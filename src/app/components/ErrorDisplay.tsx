/**
 * ErrorDisplay component — shows error messages with optional retry functionality.
 * Handles three states: auto-retry countdown, retries exhausted, and non-transient errors.
 * @module ErrorDisplay
 */

import React from "react";
import { Alert, AlertTitle, Button, Typography, Box } from "@mui/material";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import ReplayIcon from "@mui/icons-material/Replay";

export interface ErrorInfo {
  code: string;
  message: string;
  isTransient: boolean;
}

interface ErrorDisplayProps {
  error: ErrorInfo;
  onRetry?: () => void;
  retryCountdown?: number | null;
}

export const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  error,
  onRetry,
  retryCountdown,
}) => {
  const isAutoRetrying = error.isTransient && retryCountdown != null && retryCountdown > 0;
  const isRetriesExhausted = error.isTransient && onRetry && !isAutoRetrying;

  return (
    <Alert
      severity="error"
      icon={<ErrorOutlineIcon />}
      sx={{
        width: "100%",
        mt: 2,
        "& .MuiAlert-message": { width: "100%" },
      }}
    >
      <AlertTitle>{error.code === "local_mode_blocked" ? "Доступ запрещён" : "Ошибка генерации"}</AlertTitle>
      <Typography variant="body2" sx={{ mb: 1 }}>
        {error.message}
      </Typography>

      {isAutoRetrying && (
        <Typography variant="body2" color="text.secondary">
          Повтор через {retryCountdown}с...
        </Typography>
      )}

      {isRetriesExhausted && (
        <Box sx={{ mt: 1 }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={<ReplayIcon />}
            onClick={onRetry}
          >
            Повторить
          </Button>
        </Box>
      )}
    </Alert>
  );
};

export default ErrorDisplay;
