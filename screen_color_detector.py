"""Высокоскоростной отслеживатель цвета экрана с имитацией правого клика.

Скрипт контролирует центральный пиксель основного монитора и выполняет
человеко-подобный правый клик ровно один раз, как только цвет пикселя
совпадает с целевым в пределах заданного допуска.

Зависимости:
    - mss
    - numpy
    - pyautogui

Пример запуска:
    python screen_color_detector.py --color 255 0 0 --tolerance 10
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import json

import numpy as np
from mss import mss
import pyautogui


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


def parse_color(values: Sequence[int]) -> Color:
    """Преобразует переданные значения RGB в :class:`Color` после проверки."""

    if len(values) != 3:
        raise argparse.ArgumentTypeError("Ожидается ровно три компоненты RGB")
    for value in values:
        if not 0 <= value <= 255:
            raise argparse.ArgumentTypeError("Компоненты RGB должны быть в диапазоне 0-255")
    return Color(*values)


def capture_center_pixel(sct: mss.mss, region: dict) -> Color:
    """Снимает цвет центрального пикселя экрана."""

    grab = sct.grab(region)
    pixel = np.array(grab, dtype=np.uint8)[0, 0, :3]
    return Color(int(pixel[0]), int(pixel[1]), int(pixel[2]))


def human_like_right_click(x: int, y: int, *, jitter: float) -> None:
    """Эмулирует правый клик мышью с небольшой случайной погрешностью."""

    pyautogui.FAILSAFE = False
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
    pyautogui.click(button="right")
    time.sleep(random.uniform(0.05, 0.1))


def load_color_from_config(config_path: Path) -> Color:
    """Считывает целевой цвет из JSON-конфига с ключами ``r``, ``g`` и ``b``."""

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

    return parse_color(rgb_values)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Отслеживает центральный пиксель и выполняет один правый клик при совпадении цвета."
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
        help="Путь к JSON-конфигу с цветом (по умолчанию color_config.json).",
    )
    parser.add_argument(
        "--tolerance",
        type=int,
        default=5,
        help="Допустимое отклонение по каждому каналу (по умолчанию 5)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.005,
        help="Интервал между проверками в секундах (по умолчанию 0.005)",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=3.0,
        help="Радиус случайного смещения курсора для имитации человека (по умолчанию 3.0)",
    )
    args = parser.parse_args(argv)

    if args.color is not None:
        target_color = parse_color(args.color)
    else:
        target_color = load_color_from_config(args.config)
    tolerance = max(0, args.tolerance)
    interval = max(0.0, args.interval)

    with mss() as sct:
        monitor = sct.monitors[0]
        center_x = monitor["left"] + monitor["width"] // 2
        center_y = monitor["top"] + monitor["height"] // 2
        region = {"left": center_x, "top": center_y, "width": 1, "height": 1}

        print(
            f"Мониторинг центрального пикселя ({center_x}, {center_y}) на совпадение с цветом {target_color} "+
            f" при допуске ±{tolerance}."
        )
        try:
            while True:
                current_color = capture_center_pixel(sct, region)
                if current_color.within_tolerance(target_color, tolerance):
                    print(f"Целевой цвет обнаружен: {current_color}. Выполняю правый клик…")
                    human_like_right_click(center_x, center_y, jitter=args.jitter)
                    print("Правый клик выполнен. Завершение работы.")
                    return 0
                time.sleep(interval)
        except KeyboardInterrupt:
            print("Работа прервана пользователем.")
            return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
