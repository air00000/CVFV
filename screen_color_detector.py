"""Высокоскоростной отслеживатель цвета экрана с имитацией левого клика.

Скрипт контролирует центральный пиксель основного монитора и выполняет
человеко-подобный левый клик ровно один раз, как только цвет пикселя
совпадает с целевым в пределах заданного допуска. Детектор можно включать и
выключать горячей клавишей, заданной в конфиге.

Зависимости:
    - mss
    - numpy
    - pyautogui

Пример запуска:
    python screen_color_detector.py --color 255 0 0 --tolerance 10
"""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pyautogui
from mss import mss


@dataclass(frozen=True)
class Color:
    """Контейнер для хранения цвета в формате RGB."""

    r: int
    g: int
    b: int

    def within_tolerance(self, other: "Color", tolerance: int) -> bool:
        """Возвращает ``True``, если все каналы находятся в пределах допуска."""

        return (
            abs(self.r - other.r) <= tolerance
            and abs(self.g - other.g) <= tolerance
            and abs(self.b - other.b) <= tolerance
        )


@dataclass(frozen=True)
class AppConfig:
    """Глобальные настройки приложения, загружаемые из JSON."""

    color: Color
    color_tolerance: int
    base_delay: float
    trigger_delay: float
    trigger_hotkey: int | None
    always_enabled: bool


def parse_color(values: Sequence[int]) -> Color:
    """Преобразует переданные значения RGB в :class:`Color` после проверки."""

    if len(values) != 3:
        raise argparse.ArgumentTypeError("Ожидается ровно три компоненты RGB")
    for value in values:
        if not 0 <= value <= 255:
            raise argparse.ArgumentTypeError("Компоненты RGB должны быть в диапазоне 0-255")
    return Color(*values)


def parse_hotkey(value: str | int | None) -> int | None:
    """Преобразует представление клавиши в числовой виртуальный код."""

    if value is None:
        return None
    if isinstance(value, int):
        hotkey = value
    elif isinstance(value, str):
        try:
            hotkey = int(value, 0)
        except ValueError as error:
            raise ValueError(
                "Значение trigger_hotkey должно быть целым числом или строкой-числом."
            ) from error
    else:
        raise TypeError("Некорректный тип trigger_hotkey в конфиге")

    if not 0 <= hotkey <= 0xFF:
        raise ValueError("trigger_hotkey должен быть в диапазоне 0x00-0xFF")
    return hotkey


def load_app_config(config_path: Path) -> AppConfig:
    """Считывает настройки приложения из JSON-конфига."""

    try:
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Не найден файл конфигурации по пути: {config_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Ошибка чтения JSON-конфига: {error}") from error

    try:
        rgb_values = (
            int(config_data["color"]["r"]),
            int(config_data["color"]["g"]),
            int(config_data["color"]["b"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "В конфиге должен быть раздел 'color' с целыми ключами 'r', 'g', 'b'."
        ) from error

    color = parse_color(rgb_values)

    tolerance = int(config_data.get("color_tolerance", 5))
    if tolerance < 0:
        raise ValueError("color_tolerance не может быть отрицательным")

    base_delay = float(config_data.get("base_delay", 0.005))
    if base_delay < 0:
        raise ValueError("base_delay не может быть отрицательным")

    trigger_delay_ms = float(config_data.get("trigger_delay", 0.0))
    if trigger_delay_ms < 0:
        raise ValueError("trigger_delay не может быть отрицательным")
    trigger_delay = trigger_delay_ms / 1000.0

    hotkey = parse_hotkey(config_data.get("trigger_hotkey"))
    always_enabled = bool(config_data.get("always_enabled", True))

    return AppConfig(
        color=color,
        color_tolerance=tolerance,
        base_delay=base_delay,
        trigger_delay=trigger_delay,
        trigger_hotkey=hotkey,
        always_enabled=always_enabled,
    )


def capture_center_pixel(sct: mss, region: dict) -> Color:
    """Снимает цвет центрального пикселя экрана."""

    grab = sct.grab(region)
    pixel = np.array(grab, dtype=np.uint8)[0, 0, :3]
    return Color(int(pixel[0]), int(pixel[1]), int(pixel[2]))


def human_like_left_click(
    x: int,
    y: int,
    *,
    jitter: float,
    base_delay: float,
    trigger_delay: float,
) -> None:
    """Эмулирует левый клик мышью с небольшой случайной погрешностью."""

    pyautogui.FAILSAFE = False
    pre_delay = max(0.0, base_delay) + random.uniform(0.0, max(0.0, trigger_delay))
    if pre_delay:
        time.sleep(pre_delay)

    offset_x = random.uniform(-jitter, jitter)
    offset_y = random.uniform(-jitter, jitter)
    move_duration = random.uniform(0.05, 0.12)

    pyautogui.moveTo(
        x + offset_x,
        y + offset_y,
        duration=move_duration,
        tween=pyautogui.easeInOutQuad,
    )
    time.sleep(random.uniform(0.03, 0.08))
    pyautogui.click(button="left")
    time.sleep(random.uniform(0.05, 0.1))


def is_hotkey_pressed(vk_code: int) -> bool:
    """Возвращает ``True`` при нажатии виртуальной клавиши (Windows)."""

    if not sys.platform.startswith("win"):
        return False

    state = ctypes.windll.user32.GetAsyncKeyState(vk_code)
    return bool(state & 0x8000)


def describe_hotkey(vk_code: int | None) -> str:
    """Возвращает строковое представление виртуального кода для вывода."""

    if vk_code is None:
        return "(горячая клавиша не назначена)"
    return f"0x{vk_code:02X}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Отслеживает центральный пиксель и выполняет один левый клик при совпадении цвета.",
    )
    parser.add_argument(
        "--color",
        nargs=3,
        type=int,
        metavar=("R", "G", "B"),
        help="Целевой цвет RGB (например, --color 255 0 0).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("color_config.json"),
        help="Путь к JSON-конфигу с настройками (по умолчанию color_config.json).",
    )
    parser.add_argument(
        "--tolerance",
        type=int,
        help="Допустимое отклонение по каждому каналу (приоритет над конфигом)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        help="Интервал между проверками в секундах (приоритет над конфигом)",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=3.0,
        help="Радиус случайного смещения курсора для имитации человека (по умолчанию 3.0)",
    )
    parser.add_argument(
        "--trigger-delay",
        type=float,
        help="Дополнительная задержка перед кликом в миллисекундах (приоритет над конфигом)",
    )
    parser.add_argument(
        "--hotkey",
        type=str,
        help="Виртуальный код клавиши для включения/выключения в формате 0xNN",
    )
    parser.add_argument(
        "--start-enabled",
        dest="start_enabled",
        action="store_true",
        help="Принудительно запускать в активном режиме, вне зависимости от конфига",
    )
    parser.add_argument(
        "--start-disabled",
        dest="start_enabled",
        action="store_false",
        help="Принудительно запускать в пассивном режиме, вне зависимости от конфига",
    )
    parser.set_defaults(start_enabled=None)
    args = parser.parse_args(argv)

    app_config = load_app_config(args.config)

    if args.color is not None:
        target_color = parse_color(args.color)
    else:
        target_color = app_config.color

    tolerance = app_config.color_tolerance if args.tolerance is None else max(0, args.tolerance)
    interval = app_config.base_delay if args.interval is None else max(0.0, args.interval)
    trigger_delay = (
        app_config.trigger_delay
        if args.trigger_delay is None
        else max(0.0, float(args.trigger_delay) / 1000.0)
    )
    hotkey = app_config.trigger_hotkey if args.hotkey is None else parse_hotkey(args.hotkey)

    if args.start_enabled is None:
        enabled = app_config.always_enabled
    else:
        enabled = args.start_enabled

    with mss() as sct:
        monitor = sct.monitors[0]
        center_x = monitor["left"] + monitor["width"] // 2
        center_y = monitor["top"] + monitor["height"] // 2
        region = {"left": center_x, "top": center_y, "width": 1, "height": 1}

        print(
            f"Мониторинг центрального пикселя ({center_x}, {center_y}) на совпадение с цветом {target_color} "
            f"при допуске ±{tolerance}."
        )
        print(
            "Запуск детектора: "
            + ("включен" if enabled else "выключен")
            + f". Горячая клавиша {describe_hotkey(hotkey)}."
        )
        if hotkey is not None and not sys.platform.startswith("win"):
            print(
                "Предупреждение: управление горячей клавишей поддерживается только в Windows, "
                "переключение будет недоступно."
            )
        try:
            last_hotkey_state = False
            while True:
                if hotkey is not None:
                    pressed = is_hotkey_pressed(hotkey)
                    if pressed and not last_hotkey_state:
                        enabled = not enabled
                        print(
                            f"Бот {'включен' if enabled else 'выключен'} (горячая клавиша {describe_hotkey(hotkey)})."
                        )
                    last_hotkey_state = pressed

                if not enabled:
                    time.sleep(interval)
                    continue

                current_color = capture_center_pixel(sct, region)
                if current_color.within_tolerance(target_color, tolerance):
                    print(f"Целевой цвет обнаружен: {current_color}. Выполняю левый клик…")
                    human_like_left_click(
                        center_x,
                        center_y,
                        jitter=args.jitter,
                        base_delay=interval,
                        trigger_delay=trigger_delay,
                    )
                    print("Левый клик выполнен. Завершение работы.")
                    return 0
                time.sleep(interval)
        except KeyboardInterrupt:
            print("Работа прервана пользователем.")
            return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
