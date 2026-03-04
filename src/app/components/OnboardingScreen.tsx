/**
 * OnboardingScreen — Shows on first launch to introduce the app.
 * Dismissible; stores state in localStorage so it only appears once.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Sparkles, Monitor, Cloud, ArrowRight, X } from "lucide-react";

const ONBOARDING_KEY = "mg_onboarding_done";

export function useOnboarding() {
  const [dismissed, setDismissed] = useState(() => {
    return localStorage.getItem(ONBOARDING_KEY) === "1";
  });

  const dismiss = () => {
    localStorage.setItem(ONBOARDING_KEY, "1");
    setDismissed(true);
  };

  return { showOnboarding: !dismissed, dismissOnboarding: dismiss };
}

interface OnboardingScreenProps {
  onDismiss: () => void;
}

export function OnboardingScreen({ onDismiss }: OnboardingScreenProps) {
  const [step, setStep] = useState(0);

  const steps = [
    {
      title: "Добро пожаловать в Gooni Gooni",
      subtitle: "AI-платформа для генерации изображений и видео",
      icon: <Sparkles className="w-8 h-8" />,
      description:
        "Создавайте уникальные изображения и видео с помощью нейросетей. Выбирайте модели, настраивайте параметры и получайте результат за секунды.",
    },
    {
      title: "Два режима работы",
      subtitle: "Локально или в облаке — решать вам",
      icon: null,
      cards: [
        {
          icon: <Monitor className="w-5 h-5" />,
          title: "Локальный режим",
          desc: "Генерация через ComfyUI на вашем компьютере. Бесплатно, но нужна NVIDIA GPU.",
          color: "#22C55E",
        },
        {
          icon: <Cloud className="w-5 h-5" />,
          title: "Облачный режим",
          desc: "Генерация через Modal GPU в облаке. Быстро и без требований к железу.",
          color: "#4F8CFF",
        },
      ],
    },
    {
      title: "Начните прямо сейчас",
      subtitle: "Введите промпт и нажмите «Генерировать»",
      icon: <ArrowRight className="w-8 h-8" />,
      description:
        "Переключайте режимы генерации, управляйте моделями и просматривайте результаты в галерее. Всё готово!",
    },
  ];

  const current = steps[step];
  const isLast = step === steps.length - 1;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center"
        style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(16px)" }}
      >
        {/* Close button */}
        <button
          onClick={onDismiss}
          className="absolute top-6 right-6 p-2 rounded-lg transition-all duration-150"
          style={{ color: "#6B7280" }}
          onMouseEnter={(e) => { e.currentTarget.style.color = "#E5E7EB"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "#6B7280"; }}
        >
          <X className="w-5 h-5" />
        </button>

        <motion.div
          key={step}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
          className="max-w-md w-full px-8"
        >
          {/* Icon */}
          {current.icon && (
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-8"
              style={{
                background: "rgba(79,140,255,0.08)",
                border: "1px solid rgba(79,140,255,0.15)",
                color: "#4F8CFF",
              }}
            >
              {current.icon}
            </div>
          )}

          {/* Title */}
          <h1
            className="text-2xl font-semibold text-center mb-2"
            style={{ color: "#E5E7EB", fontFamily: "'Space Grotesk', sans-serif" }}
          >
            {current.title}
          </h1>
          <p className="text-sm text-center mb-8" style={{ color: "#6B7280" }}>
            {current.subtitle}
          </p>

          {/* Content */}
          {current.description && (
            <p className="text-sm text-center leading-relaxed mb-8" style={{ color: "#9CA3AF" }}>
              {current.description}
            </p>
          )}

          {current.cards && (
            <div className="space-y-3 mb-8">
              {current.cards.map((card) => (
                <div
                  key={card.title}
                  className="flex items-start gap-4 p-4 rounded-xl"
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: `1px solid ${card.color}22`,
                  }}
                >
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: `${card.color}15`, color: card.color }}
                  >
                    {card.icon}
                  </div>
                  <div>
                    <p className="text-sm font-medium" style={{ color: "#E5E7EB" }}>{card.title}</p>
                    <p className="text-xs mt-1" style={{ color: "#6B7280" }}>{card.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between">
            {/* Dots */}
            <div className="flex gap-2">
              {steps.map((_, i) => (
                <div
                  key={i}
                  className="w-2 h-2 rounded-full transition-all duration-200"
                  style={{
                    background: i === step ? "#4F8CFF" : "rgba(255,255,255,0.1)",
                    width: i === step ? 20 : 8,
                  }}
                />
              ))}
            </div>

            {/* Button */}
            <button
              onClick={() => {
                if (isLast) {
                  onDismiss();
                } else {
                  setStep(step + 1);
                }
              }}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm transition-all duration-150"
              style={{
                background: "rgba(79,140,255,0.15)",
                border: "1px solid rgba(79,140,255,0.3)",
                color: "#4F8CFF",
                fontFamily: "'Space Grotesk', sans-serif",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(79,140,255,0.25)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(79,140,255,0.15)";
              }}
            >
              {isLast ? "Начать" : "Далее"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
