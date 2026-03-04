import numpy as np
import torch

def validate_output(image_or_frames):
    """Проверяет что результат не пустой и не артефактный"""
    if image_or_frames is None:
        raise ValueError("ОШИБКА: Результат None.")
        
    if hasattr(image_or_frames, 'frames'):
        data = np.array(image_or_frames.frames[0])
    else:
        data = np.array(image_or_frames)
    
    mean_val = data.mean()
    std_val = data.std()
    
    if mean_val < 5:
        raise ValueError(f"ОШИБКА: Серый/чёрный экран. Mean={mean_val:.2f}")
    if mean_val > 250:
        raise ValueError(f"ОШИБКА: Белый экран. Mean={mean_val:.2f}")
    if std_val < 10:
        raise ValueError(f"ОШИБКА: Слишком мало вариаций (артефакт?). Std={std_val:.2f}")
    if std_val < 30 and mean_val > 100 and mean_val < 140:
        raise ValueError(f"ОШИБКА: Обнаружен паттерн серого экрана с точками (Низкая дисперсия на сером фоне). Std={std_val:.2f}")
    
    print(f"✅ Валидация прошла: mean={mean_val:.2f}, std={std_val:.2f}")
    return True

def validate_latents(latents: torch.Tensor):
    """Проверяет латенты на наличие NaN значений перед декодированием"""
    if torch.isnan(latents).any() or torch.isinf(latents).any():
        raise ValueError("ОШИБКА: Латенты содержат NaN или Inf значения. Необходим фикс VAE или float32 кастинг.")
    return True
