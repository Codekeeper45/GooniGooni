"""
Deployer — runs `modal deploy` with per-account credentials.

Each account has its own MODAL_TOKEN_ID + MODAL_TOKEN_SECRET.
We spawn a subprocess with those env vars injected so that
`modal deploy` authenticates as that specific workspace.

The deploy runs in a background thread so the API response is not blocked.
Status transitions:
  pending → (deploy running) → ready
                             → failed
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import logging
import time
from pathlib import Path
from typing import Optional

import accounts as acc_store
import httpx
from admin_security import _ensure_audit_table, _log_action

# Path to the main Modal app file (relative to repo root)
BACKEND_DIR = Path(__file__).parent
APP_FILE = str(BACKEND_DIR / "app.py")
logger = logging.getLogger("deployer")
MODAL_TARGET_ENV = (os.environ.get("MODAL_TARGET_ENV", "main").strip() or "main")
ACCOUNT_DEPLOY_TIMEOUT_SECONDS = max(60, int(os.environ.get("ACCOUNT_DEPLOY_TIMEOUT_SECONDS", "300")))
ACCOUNT_DEPLOY_MAX_RETRIES = max(1, int(os.environ.get("ACCOUNT_DEPLOY_MAX_RETRIES", "3")))
ACCOUNT_DEPLOY_RETRY_BACKOFF_SECONDS = max(0.0, float(os.environ.get("ACCOUNT_DEPLOY_RETRY_BACKOFF_SECONDS", "10")))
ACCOUNT_DEPLOY_RETRY_MAX_BACKOFF_SECONDS = max(
    ACCOUNT_DEPLOY_RETRY_BACKOFF_SECONDS,
    float(os.environ.get("ACCOUNT_DEPLOY_RETRY_MAX_BACKOFF_SECONDS", "30")),
)
ACCOUNT_HEALTH_ATTEMPTS = max(1, int(os.environ.get("ACCOUNT_HEALTH_ATTEMPTS", "24")))
ACCOUNT_HEALTH_INTERVAL_SECONDS = max(1.0, float(os.environ.get("ACCOUNT_HEALTH_INTERVAL_SECONDS", "5")))
ACCOUNT_WARMUP_REQUIRED = (os.environ.get("ACCOUNT_WARMUP_REQUIRED", "1").strip().lower() in {"1", "true", "yes", "on"})
ACCOUNT_WARMUP_TOTAL_TIMEOUT_SECONDS = max(30.0, float(os.environ.get("ACCOUNT_WARMUP_TOTAL_TIMEOUT_SECONDS", "720")))
ACCOUNT_WARMUP_POLL_INTERVAL_SECONDS = max(1.0, float(os.environ.get("ACCOUNT_WARMUP_POLL_INTERVAL_SECONDS", "3")))
REQUIRED_WARMUP_MODELS = ("anisora", "phr00t", "pony", "flux")

_SHARED_SECRET_BINDINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gooni-api-key", ("API_KEY",)),
    ("gooni-admin", ("ADMIN_LOGIN", "ADMIN_PASSWORD_HASH")),
    ("gooni-accounts", ("ACCOUNTS_ENCRYPT_KEY",)),
    ("huggingface", ("HF_TOKEN",)),
)


def required_shared_env_keys() -> tuple[str, ...]:
    seen: list[str] = []
    for _, keys in _SHARED_SECRET_BINDINGS:
        for key in keys:
            if key not in seen:
                seen.append(key)
    return tuple(seen)


def get_missing_shared_env_keys() -> list[str]:
    missing: list[str] = []
    for key in required_shared_env_keys():
        if not os.environ.get(key, "").strip():
            missing.append(key)
    return missing


def _redact_sensitive_text(text: str, account: Optional[dict] = None) -> str:
    redacted = text
    secrets: list[str] = []
    for key in required_shared_env_keys():
        value = os.environ.get(key, "").strip()
        if value:
            secrets.append(value)
    if account:
        for key in ("token_id", "token_secret"):
            value = str(account.get(key, "")).strip()
            if value:
                secrets.append(value)

    for value in secrets:
        # Avoid masking generic short strings.
        if len(value) >= 6:
            redacted = redacted.replace(value, "***")
    return redacted


def _extract_subprocess_error(result: subprocess.CompletedProcess, account: Optional[dict]) -> str:
    raw = result.stderr or result.stdout or "Unknown deploy error"
    return _redact_sensitive_text(raw, account)[:500]


def _normalize_onboarding_error(code: str, error: str, account: Optional[dict]) -> str:
    redacted = _redact_sensitive_text(error or "Unknown error", account).strip()
    if not redacted:
        redacted = "Unknown error"
    return f"{code}: {redacted[:460]}"


def _audit_onboarding_step(
    *,
    account: Optional[dict],
    action: str,
    success: bool,
    details: str = "",
) -> None:
    try:
        _ensure_audit_table()
        account_id = str((account or {}).get("id") or "unknown")
        label = str((account or {}).get("label") or "")
        payload = f"account_id={account_id}; label={label}"
        if details:
            payload = f"{payload}; {details}"
        _log_action("system", action, payload[:500], success=success)
    except Exception as exc:
        logger.warning("Onboarding audit log failed: %s", exc)


def _audit_failure_outcome(account_id: str, account: Optional[dict], reason_code: str) -> None:
    row = acc_store.get_account(account_id)
    status = (row or {}).get("status", "unknown")
    action = "account_disabled" if status == "disabled" else "account_failed"
    _audit_onboarding_step(
        account=account,
        action=action,
        success=False,
        details=f"reason={reason_code}; status={status}",
    )


def _deploy_backoff_seconds(attempt: int) -> float:
    if attempt <= 0:
        return 0.0
    return min(
        ACCOUNT_DEPLOY_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)),
        ACCOUNT_DEPLOY_RETRY_MAX_BACKOFF_SECONDS,
    )


def _is_health_429_quota_error(error: str) -> bool:
    lower = (error or "").lower()
    return (
        "health-check status=429" in lower
        or ("429" in lower and "health" in lower)
        or "billing cycle spend limit reached" in lower
        or "spend limit" in lower
        or "quota" in lower
    )


def _sync_workspace_secrets(env: dict[str, str], account: dict) -> None:
    missing = get_missing_shared_env_keys()
    if missing:
        raise RuntimeError(
            "Missing required shared env: " + ", ".join(missing)
        )

    for secret_name, env_keys in _SHARED_SECRET_BINDINGS:
        key_values = [f"{env_key}={os.environ[env_key].strip()}" for env_key in env_keys]
        cmd = [
            sys.executable,
            "-m",
            "modal",
            "secret",
            "create",
            "-e",
            MODAL_TARGET_ENV,
            "--force",
            secret_name,
            *key_values,
        ]
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            error = _extract_subprocess_error(result, account)
            raise RuntimeError(f"Secret sync failed for {secret_name}: {error}")


def deploy_account(account_id: str) -> None:
    """
    Deploy backend/app.py using the account's Modal credentials.
    Updates account status to 'ready' or 'failed'.
    Should be called in a background thread (non-blocking for the caller).
    """
    account = acc_store.get_account(account_id)
    if account is None:
        return

    # Minimal env: only pass what modal deploy actually needs.
    # Never forward parent secrets (API_KEY, ADMIN_KEY, ACCOUNTS_ENCRYPT_KEY, etc.).
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "MODAL_TOKEN_ID": account["token_id"],
        "MODAL_TOKEN_SECRET": account["token_secret"],
    }

    def _commit_volume() -> None:
        try:
            import modal as _modal
            _modal.Volume.from_name("results").commit()
        except Exception:
            pass  # best-effort; container-local reads remain consistent

    try:
        _audit_onboarding_step(
            account=account,
            action="account_onboarding_started",
            success=True,
            details="step=started",
        )
        acc_store.update_account_status(account_id, "checking", error=None)
        _commit_volume()
        _audit_onboarding_step(
            account=account,
            action="account_tokens_check_started",
            success=True,
            details="step=tokens_check",
        )
        try:
            _sync_workspace_secrets(env, account)
        except Exception as exc:
            raw_error = str(exc)
            detected_failure_type, _ = acc_store._classify_error(raw_error)
            if detected_failure_type == "auth_failed":
                error_code = "invalid_tokens"
                failure_type = "auth_failed"
            elif detected_failure_type == "config_failed":
                error_code = "config_failed"
                failure_type = "config_failed"
            else:
                error_code = "config_failed"
                failure_type = detected_failure_type
            normalized_error = _normalize_onboarding_error(error_code, raw_error, account)
            acc_store.mark_account_failed(
                account_id,
                normalized_error,
                failure_type=failure_type,
            )
            _audit_onboarding_step(
                account=account,
                action="account_tokens_check_failed",
                success=False,
                details=f"step=tokens_check; code={error_code}; error={normalized_error[:180]}",
            )
            _audit_failure_outcome(account_id, account, error_code)
            _commit_volume()
            return
        _audit_onboarding_step(
            account=account,
            action="account_tokens_check_passed",
            success=True,
            details="step=tokens_check",
        )

        workspace: Optional[str] = None
        deploy_error: Optional[str] = None
        acc_store.update_account_status(account_id, "deploying", error=None)
        _audit_onboarding_step(
            account=account,
            action="account_deploy_started",
            success=True,
            details="step=deploy",
        )
        for attempt in range(1, ACCOUNT_DEPLOY_MAX_RETRIES + 1):
            try:
                logger.info(
                    "deploy_account attempt=%s/%s account_id=%s",
                    attempt,
                    ACCOUNT_DEPLOY_MAX_RETRIES,
                    account_id,
                )
                result = subprocess.run(
                    [sys.executable, "-m", "modal", "deploy", "-e", MODAL_TARGET_ENV, APP_FILE],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=ACCOUNT_DEPLOY_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                deploy_error = (
                    f"Deploy timed out after {ACCOUNT_DEPLOY_TIMEOUT_SECONDS} seconds "
                    f"(attempt {attempt}/{ACCOUNT_DEPLOY_MAX_RETRIES})"
                )
            else:
                if result.returncode == 0:
                    workspace = _extract_workspace(result.stdout)
                    if workspace:
                        break
                    deploy_error = "Deploy succeeded but workspace was not detected"
                else:
                    deploy_error = _extract_subprocess_error(result, account)

            if attempt < ACCOUNT_DEPLOY_MAX_RETRIES:
                backoff = _deploy_backoff_seconds(attempt)
                if backoff > 0:
                    time.sleep(backoff)

        if not workspace:
            error = deploy_error or "Deploy failed"
            normalized_error = _normalize_onboarding_error("deploy_failed", error, account)
            failure_type, _ = acc_store._classify_error(error)
            acc_store.mark_account_failed(
                account_id,
                normalized_error,
                failure_type=failure_type,
            )
            _audit_onboarding_step(
                account=account,
                action="account_deploy_failed",
                success=False,
                details=f"step=deploy; code=deploy_failed; error={normalized_error[:180]}",
            )
            _audit_failure_outcome(account_id, account, "deploy_failed")
            _commit_volume()
            return
        acc_store.update_account_status(account_id, "checking", workspace=workspace, error=None)
        _audit_onboarding_step(
            account=account,
            action="account_deploy_passed",
            success=True,
            details=f"step=deploy; workspace={workspace}",
        )
        _audit_onboarding_step(
            account=account,
            action="account_healthcheck_started",
            success=True,
            details=f"step=health_check; workspace={workspace}",
        )

        ok, health_error = _wait_for_workspace_health(
            workspace,
            account_id=account_id,
            attempts=ACCOUNT_HEALTH_ATTEMPTS,
            interval_seconds=ACCOUNT_HEALTH_INTERVAL_SECONDS,
        )
        if not ok:
            error = health_error or "health check failed"
            normalized_error = _normalize_onboarding_error("health_failed", error, account)
            if _is_health_429_quota_error(error):
                failure_type = "quota_exceeded"
            else:
                failure_type, _ = acc_store._classify_error(error)
            acc_store.mark_account_failed(
                account_id,
                normalized_error,
                failure_type=failure_type,
            )
            _audit_onboarding_step(
                account=account,
                action="account_healthcheck_failed",
                success=False,
                details=f"step=health_check; code=health_failed; error={normalized_error[:180]}",
            )
            _audit_failure_outcome(account_id, account, "health_failed")
            _commit_volume()
            return
        _audit_onboarding_step(
            account=account,
            action="account_healthcheck_passed",
            success=True,
            details=f"step=health_check; workspace={workspace}",
        )
        _audit_onboarding_step(
            account=account,
            action="account_warmup_started",
            success=True,
            details=f"step=warmup; workspace={workspace}",
        )

        warmup_ok, warmup_error = _trigger_workspace_warmup(workspace, account_id=account_id)
        if ACCOUNT_WARMUP_REQUIRED and not warmup_ok:
            error = warmup_error or "Required warmup failed"
            normalized_error = _normalize_onboarding_error("warmup_failed", error, account)
            failure_type, _ = acc_store._classify_error(error)
            acc_store.mark_account_failed(
                account_id,
                normalized_error,
                failure_type=failure_type,
            )
            _audit_onboarding_step(
                account=account,
                action="account_warmup_failed",
                success=False,
                details=f"step=warmup; code=warmup_failed; error={normalized_error[:180]}",
            )
            _audit_failure_outcome(account_id, account, "warmup_failed")
            _commit_volume()
            return
        if not warmup_ok:
            logger.warning("workspace optional warmup failed: workspace=%s error=%s", workspace, warmup_error)
            _audit_onboarding_step(
                account=account,
                action="account_warmup_failed",
                success=False,
                details=f"step=warmup_optional; workspace={workspace}; error={str(warmup_error)[:180]}",
            )
        else:
            _audit_onboarding_step(
                account=account,
                action="account_warmup_passed",
                success=True,
                details=f"step=warmup; workspace={workspace}",
            )

        acc_store.update_account_status(account_id, "ready", workspace=workspace, error=None)
        _audit_onboarding_step(
            account=account,
            action="account_ready",
            success=True,
            details=f"workspace={workspace}",
        )
        _commit_volume()

    except Exception as exc:
        raw_error = str(exc)
        error = _normalize_onboarding_error("deploy_failed", raw_error, account)
        failure_type, _ = acc_store._classify_error(raw_error)
        acc_store.mark_account_failed(
            account_id,
            error,
            failure_type=failure_type,
        )
        _audit_onboarding_step(
            account=account,
            action="account_onboarding_failed",
            success=False,
            details=f"code=deploy_failed; error={error[:180]}",
        )
        _audit_failure_outcome(account_id, account, "deploy_failed")
        _commit_volume()


def deploy_account_async(account_id: str) -> threading.Thread:
    """
    Kick off deploy_account in a background thread.
    Returns the thread (already started).
    """
    thread = threading.Thread(
        target=deploy_account,
        args=(account_id,),
        daemon=True,
        name=f"deploy-{account_id[:8]}",
    )
    thread.start()
    return thread


def deploy_all_accounts() -> list[threading.Thread]:
    """
    Redeploy ALL ready (and failed) accounts simultaneously.
    Skips accounts that are 'disabled'.
    Returns list of started threads.
    """
    all_accounts = acc_store.list_accounts()
    threads = []
    for account in all_accounts:
        if account["status"] in {"disabled", "checking"}:
            continue
        thread = deploy_account_async(account["id"])
        threads.append(thread)
    return threads


def _extract_workspace(output: str) -> Optional[str]:
    """
    Try to extract the workspace name from `modal deploy` stdout.
    Modal typically prints something like:
      ✓ Deployed app at https://WORKSPACE--gooni-api.modal.run
    """
    for line in output.splitlines():
        if "modal.run" in line:
            # Extract WORKSPACE from https://WORKSPACE--gooni-api.modal.run
            try:
                url = [w for w in line.split() if "modal.run" in w][0]
                workspace = url.split("//")[1].split("--")[0]
                return workspace
            except (IndexError, ValueError):
                pass
    return None


def _wait_for_workspace_health(
    workspace: str,
    account_id: Optional[str] = None,
    attempts: int = ACCOUNT_HEALTH_ATTEMPTS,
    interval_seconds: float = ACCOUNT_HEALTH_INTERVAL_SECONDS,
    cache_ttl_seconds: int = 300,
) -> tuple[bool, Optional[str]]:
    """
    Wait for workspace health check to pass.

    If account_id is provided, health check results are cached in the DB.
    A cached positive result younger than cache_ttl_seconds is returned
    immediately without making HTTP requests.
    """
    # Check cache first
    if account_id:
        account = acc_store.get_account(account_id)
        if account and account.get("last_health_check") and account.get("health_check_result") == "ok":
            from datetime import datetime, timezone
            try:
                cached_at = datetime.fromisoformat(account["last_health_check"])
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age < cache_ttl_seconds:
                    logger.info("workspace health check cache hit: %s (age=%.0fs)", workspace, age)
                    return True, None
            except Exception:
                pass  # Cache miss on malformed timestamp

    url = f"https://{workspace}--gooni-api.modal.run/health"
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
    last_error = "health-check did not run"
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("ok") is True:
                    logger.info("workspace health check passed: %s", workspace)
                    if account_id:
                        acc_store.update_health_check(account_id, "ok")
                    return True, None
            body_hint = (response.text or "").strip()
            if body_hint:
                body_hint = body_hint[:180]
                last_error = f"health-check status={response.status_code}: {body_hint}"
            else:
                last_error = f"health-check status={response.status_code}"
        except Exception as exc:
            last_error = f"health-check error: {exc}"
        if attempt < attempts:
            time.sleep(interval_seconds)

    # Cache negative result
    if account_id:
        acc_store.update_health_check(account_id, f"failed: {last_error}")

    return False, last_error


def _wait_for_warmup_tasks(
    workspace: str,
    model_task_ids: dict[str, str],
    headers: dict[str, str],
    total_timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[bool, Optional[str]]:
    deadline = time.monotonic() + total_timeout_seconds
    pending = dict(model_task_ids)
    status_url_base = f"https://{workspace}--gooni-api.modal.run/status/"
    timeout = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
    last_error = ""

    with httpx.Client(timeout=timeout) as client:
        while pending:
            if time.monotonic() >= deadline:
                models = ", ".join(sorted(pending.keys()))
                extra = f"; last_error={last_error}" if last_error else ""
                return False, f"warmup timed out after {int(total_timeout_seconds)}s; pending: {models}{extra}"

            for model, task_id in list(pending.items()):
                try:
                    response = client.get(f"{status_url_base}{task_id}", headers=headers)
                except Exception as exc:
                    last_error = f"status poll error for {model}: {exc}"
                    continue

                if response.status_code != 200:
                    body_hint = (response.text or "").strip()[:120]
                    if body_hint:
                        last_error = f"status poll {model}: http {response.status_code} ({body_hint})"
                    else:
                        last_error = f"status poll {model}: http {response.status_code}"
                    continue

                try:
                    payload = response.json()
                except Exception:
                    last_error = f"status poll {model}: invalid JSON"
                    continue

                status_value = str(payload.get("status", "")).lower()
                if status_value == "done":
                    pending.pop(model, None)
                    continue
                if status_value == "failed":
                    reason = payload.get("error_msg") or payload.get("stage_detail") or "unknown warmup failure"
                    return False, f"warmup failed for {model}: {reason}"

            if pending:
                time.sleep(poll_interval_seconds)

    return True, None


def _trigger_workspace_warmup(workspace: str, account_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Trigger lane warmup and wait until all required model lanes report terminal success.
    """
    enabled = (os.environ.get("ENABLE_LANE_WARMUP", "1").strip().lower() in {"1", "true", "yes", "on"})
    if not enabled:
        if ACCOUNT_WARMUP_REQUIRED:
            return False, "Warmup is disabled by ENABLE_LANE_WARMUP."
        return True, None

    api_key = os.environ.get("API_KEY", "").strip()
    if not api_key:
        return False, "API_KEY is missing; cannot trigger warmup"

    retries = max(1, int(os.environ.get("WARMUP_RETRIES", "2")))
    connect_timeout = float(os.environ.get("WARMUP_CONNECT_TIMEOUT_SECONDS", "5"))
    read_timeout = float(os.environ.get("WARMUP_TIMEOUT_SECONDS", "25"))
    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=10.0, pool=5.0)
    url = f"https://{workspace}--gooni-api.modal.run/warmup"
    headers = {"X-API-Key": api_key}
    last_error = "warmup did not run"

    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers)
            if response.status_code != 200:
                last_error = f"warmup status={response.status_code}"
            else:
                payload = response.json()
                scheduled = payload.get("scheduled") or []
                model_task_ids: dict[str, str] = {}
                for entry in scheduled:
                    model = str(entry.get("model", "")).lower()
                    task_id = str(entry.get("task_id", "")).strip()
                    if model in REQUIRED_WARMUP_MODELS and task_id:
                        model_task_ids[model] = task_id

                missing_models = sorted(set(REQUIRED_WARMUP_MODELS) - set(model_task_ids.keys()))
                if missing_models:
                    errors = payload.get("errors") or []
                    last_error = (
                        f"warmup missing models: {', '.join(missing_models)}"
                        + (f"; errors={errors}" if errors else "")
                    )
                else:
                    ok, poll_error = _wait_for_warmup_tasks(
                        workspace=workspace,
                        model_task_ids=model_task_ids,
                        headers=headers,
                        total_timeout_seconds=ACCOUNT_WARMUP_TOTAL_TIMEOUT_SECONDS,
                        poll_interval_seconds=ACCOUNT_WARMUP_POLL_INTERVAL_SECONDS,
                    )
                    if ok:
                        logger.info("workspace warmup completed: %s", workspace)
                        if account_id:
                            acc_store.update_health_check(account_id, "ok+warmed")
                        return True, None
                    last_error = poll_error or "warmup status polling failed"
        except Exception as exc:
            last_error = f"warmup error: {exc}"

        if attempt < retries:
            time.sleep(2.0)

    logger.warning("workspace warmup failed: workspace=%s error=%s", workspace, last_error)
    if account_id:
        acc_store.update_health_check(account_id, f"warmup_failed: {last_error}")
    return False, last_error
