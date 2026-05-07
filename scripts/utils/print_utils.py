#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公共打印工具模块

提供统一的颜色化打印功能，并带一个零依赖的终端仪表盘：
- 不同级别的消息（成功、警告、错误、信息、进度）
- 格式化的标题和步骤显示
- 自动检测终端是否支持颜色
- 长任务阶段状态与 heartbeat
"""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence


class Colors:
    """ANSI 颜色代码"""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    DIM = "\033[2m"
    END = "\033[0m"


def _stdout_is_tty() -> bool:
    return bool(hasattr(sys.stdout, "isatty") and sys.stdout.isatty())


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@dataclass
class _HeartbeatState:
    label: str
    interval_seconds: float
    tty_dynamic: bool
    frames: Sequence[str]


class _HeartbeatHandle:
    """后台 heartbeat 控制器"""

    def __init__(self, dashboard: "TerminalDashboard", state: _HeartbeatState):
        self.dashboard = dashboard
        self.state = state
        self.started_at = time.time()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "_HeartbeatHandle":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self, final_message: Optional[str] = None):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        if final_message:
            self.dashboard.note_event(final_message)

    def _run(self):
        interval = max(0.2, self.state.interval_seconds)
        idx = 0
        while not self._stop_event.wait(interval):
            elapsed = _format_elapsed(time.time() - self.started_at)
            frame = self.state.frames[idx % len(self.state.frames)]
            idx += 1
            self.dashboard.emit_heartbeat(
                label=self.state.label,
                elapsed=elapsed,
                frame=frame,
                tty_dynamic=self.state.tty_dynamic,
            )


class TerminalDashboard:
    """轻量终端仪表盘"""

    FRAMES = ("[=   ]", "[==  ]", "[=== ]", "[ ===]", "[  ==]", "[   =]")

    def __init__(self):
        self.interactive = (
            _stdout_is_tty()
            and os.getenv("TERM", "").lower() != "dumb"
            and os.getenv("FINANCIAL_REPORT_PLAIN_LOGS", "0") != "1"
        )
        self._lock = threading.RLock()
        self.title = "Financial Report"
        self.total_steps: Optional[int] = None
        self.current_step: Optional[int] = None
        self.current_stage = "待启动"
        self.current_detail = ""
        self.recent_event = "初始化中"
        self.session_started_at = time.time()
        self.stage_started_at = time.time()
        self._last_render_lines = 0
        self._frame_index = 0

    def configure(self, *, title: Optional[str] = None, total_steps: Optional[int] = None):
        with self._lock:
            if title:
                self.title = title
            if total_steps is not None:
                self.total_steps = total_steps
            self._render()

    def start_stage(
        self,
        name: str,
        *,
        step: Optional[int] = None,
        total: Optional[int] = None,
        detail: Optional[str] = None,
    ):
        with self._lock:
            if total is not None:
                self.total_steps = total
            if step is not None:
                self.current_step = step
            self.current_stage = name
            self.current_detail = detail or ""
            self.recent_event = detail or f"进入阶段: {name}"
            self.stage_started_at = time.time()
            if self.interactive:
                self._render()
            else:
                prefix = self._stage_prefix()
                message = f"{prefix}{name}"
                if detail:
                    message = f"{message} - {detail}"
                print(message)

    def update_stage(self, detail: str):
        with self._lock:
            self.current_detail = detail
            self.recent_event = detail
            if self.interactive:
                self._render()
            else:
                print(f"[状态] {detail}")

    def finish_stage(self, summary: Optional[str] = None, duration: bool = True):
        with self._lock:
            text = summary or f"{self.current_stage} 完成"
            if duration:
                elapsed = _format_elapsed(time.time() - self.stage_started_at)
                text = f"{text} ({elapsed})"
            self.recent_event = text
            if self.interactive:
                self._render()
            else:
                print(f"[完成] {text}")

    def note_event(self, event: str):
        with self._lock:
            self.recent_event = event
            if self.interactive:
                self._render()
            else:
                print(f"[事件] {event}")

    def emit_heartbeat(self, *, label: str, elapsed: str, frame: str, tty_dynamic: bool = True):
        with self._lock:
            heartbeat_text = f"{label} 进行中 {frame} 已耗时 {elapsed}"
            self.recent_event = heartbeat_text
            if self.interactive and tty_dynamic:
                self._render()
            else:
                print(f"[心跳] {heartbeat_text}")

    @contextmanager
    def heartbeat(
        self,
        label: str,
        *,
        interval_seconds: float = 8.0,
        tty_dynamic: bool = True,
        frames: Optional[Sequence[str]] = None,
    ) -> Iterator[_HeartbeatHandle]:
        state = _HeartbeatState(
            label=label,
            interval_seconds=interval_seconds,
            tty_dynamic=tty_dynamic,
            frames=tuple(frames or self.FRAMES),
        )
        handle = _HeartbeatHandle(self, state).start()
        try:
            yield handle
        finally:
            handle.stop()

    def _stage_prefix(self) -> str:
        if self.current_step and self.total_steps:
            return f"[{self.current_step}/{self.total_steps}] "
        return ""

    def _progress_bar(self, width: int = 20) -> str:
        if not self.current_step or not self.total_steps or self.total_steps <= 0:
            return "-" * width
        filled = min(width, max(0, round(width * self.current_step / self.total_steps)))
        return "=" * filled + "-" * (width - filled)

    def _render(self):
        if not self.interactive:
            return

        total_elapsed = _format_elapsed(time.time() - self.session_started_at)
        stage_elapsed = _format_elapsed(time.time() - self.stage_started_at)
        self._frame_index = (self._frame_index + 1) % len(self.FRAMES)
        pulse = self.FRAMES[self._frame_index]
        stage_prefix = self._stage_prefix() or "[--] "

        lines = [
            self._colorize(f"┌─ {self.title} {pulse}", Colors.BOLD + Colors.CYAN),
            self._colorize(
                f"│ 阶段  {stage_prefix}{self.current_stage}",
                Colors.CYAN,
            ),
            self._colorize(
                f"│ 进度  [{self._progress_bar()}]  总耗时 {total_elapsed}  当前阶段 {stage_elapsed}",
                Colors.MAGENTA,
            ),
            self._colorize(
                f"│ 动作  {self.current_detail or '等待中'}",
                Colors.BLUE,
            ),
            self._colorize(
                f"│ 事件  {self.recent_event}",
                Colors.GREEN,
            ),
            self._colorize("└" + "─" * 58, Colors.BOLD + Colors.CYAN),
        ]

        output = sys.stdout
        if self._last_render_lines:
            output.write(f"\033[{self._last_render_lines}F")
        for idx, line in enumerate(lines):
            output.write("\033[2K")
            output.write(line)
            output.write("\n")
        output.flush()
        self._last_render_lines = len(lines)

    def _colorize(self, text: str, color: str) -> str:
        if self.interactive:
            return f"{color}{text}{Colors.END}"
        return text


class PrintUtils:
    """打印工具类"""

    def __init__(self, enable_colors: Optional[bool] = None):
        if enable_colors is None:
            self.enable_colors = (_stdout_is_tty() and sys.platform != "win32") or sys.platform == "win32"
        else:
            self.enable_colors = enable_colors
        self.dashboard = TerminalDashboard()

    def _colorize(self, text: str, color: str) -> str:
        if self.enable_colors:
            return f"{color}{text}{Colors.END}"
        return text

    def print_header(self, text: str, width: int = 60):
        separator = "=" * width
        print(f"\n{self._colorize(separator, Colors.BOLD + Colors.CYAN)}")
        print(f"{self._colorize(text.center(width), Colors.BOLD + Colors.CYAN)}")
        print(f"{self._colorize(separator, Colors.BOLD + Colors.CYAN)}\n")

    def print_success(self, text: str):
        print(f"{self._colorize('OK', Colors.GREEN)} {text}")

    def print_warning(self, text: str):
        print(f"{self._colorize('WARN', Colors.YELLOW)} {text}")

    def print_error(self, text: str):
        print(f"{self._colorize('ERR', Colors.RED)} {text}")

    def print_info(self, text: str):
        print(f"{self._colorize('INFO', Colors.BLUE)} {text}")

    def print_progress(self, text: str):
        print(f"{self._colorize('RUN', Colors.MAGENTA)} {text}")

    def print_step(self, step: int, total: int, text: str):
        print(f"{self._colorize(f'[{step}/{total}]', Colors.CYAN)} {text}")

    def print_section(self, text: str):
        print(f"\n{self._colorize('-' * 50, Colors.CYAN)}")
        print(f"{self._colorize(text, Colors.BOLD + Colors.CYAN)}")
        print(f"{self._colorize('-' * 50, Colors.CYAN)}")

    def print_table_header(self, headers: list, widths: Optional[list] = None):
        if widths is None:
            widths = [20] * len(headers)
        header_line = " | ".join(f"{h:^{w}}" for h, w in zip(headers, widths))
        print(f"{self._colorize(header_line, Colors.BOLD)}")
        separator = "-+-".join("-" * w for w in widths)
        print(f"{self._colorize(separator, Colors.CYAN)}")

    def print_table_row(self, row: list, widths: Optional[list] = None):
        if widths is None:
            widths = [20] * len(row)
        row_line = " | ".join(f"{str(cell):^{w}}" for cell, w in zip(row, widths))
        print(row_line)

    def print_statistics(self, stats: dict):
        print(f"\n{self._colorize('Stats', Colors.BOLD + Colors.CYAN)}")
        for key, value in stats.items():
            if isinstance(value, (int, float)):
                if isinstance(value, int) and value > 1000:
                    value_str = f"{value:,}"
                else:
                    value_str = str(value)
            else:
                value_str = str(value)
            print(f"  {self._colorize(key, Colors.BLUE)}: {value_str}")

    def print_file_info(self, file_type: str, file_path: str):
        print(f"{self._colorize('FILE', Colors.GREEN)} {file_type}: {file_path}")

    def print_time_info(self, operation: str, duration: float):
        print(f"{self._colorize('TIME', Colors.YELLOW)} {operation} 耗时: {duration:.2f}秒")

    def print_count(self, item: str, count: int, total: Optional[int] = None):
        if total is not None:
            print(f"{self._colorize('CNT', Colors.CYAN)} {item}: {count:,}/{total:,}")
        else:
            print(f"{self._colorize('CNT', Colors.CYAN)} {item}: {count:,}")


printer = PrintUtils()


def print_header(text: str, width: int = 60):
    printer.print_header(text, width)


def print_success(text: str):
    printer.print_success(text)


def print_warning(text: str):
    printer.print_warning(text)


def print_error(text: str):
    printer.print_error(text)


def print_info(text: str):
    printer.print_info(text)


def print_progress(text: str):
    printer.print_progress(text)


def print_step(step: int, total: int, text: str):
    printer.print_step(step, total, text)


def print_section(text: str):
    printer.print_section(text)


def print_table_header(headers: list, widths: Optional[list] = None):
    printer.print_table_header(headers, widths)


def print_table_row(row: list, widths: Optional[list] = None):
    printer.print_table_row(row, widths)


def print_statistics(stats: dict):
    printer.print_statistics(stats)


def print_file_info(file_type: str, file_path: str):
    printer.print_file_info(file_type, file_path)


def print_time_info(operation: str, duration: float):
    printer.print_time_info(operation, duration)


def print_count(item: str, count: int, total: Optional[int] = None):
    printer.print_count(item, count, total)


def configure_dashboard(*, title: Optional[str] = None, total_steps: Optional[int] = None):
    printer.dashboard.configure(title=title, total_steps=total_steps)


def start_stage(
    name: str,
    *,
    step: Optional[int] = None,
    total: Optional[int] = None,
    detail: Optional[str] = None,
):
    printer.dashboard.start_stage(name, step=step, total=total, detail=detail)


def update_stage(detail: str):
    printer.dashboard.update_stage(detail)


def finish_stage(summary: Optional[str] = None, duration: bool = True):
    printer.dashboard.finish_stage(summary=summary, duration=duration)


def note_event(event: str):
    printer.dashboard.note_event(event)


@contextmanager
def heartbeat(
    label: str,
    *,
    interval_seconds: float = 8.0,
    tty_dynamic: bool = True,
    frames: Optional[Sequence[str]] = None,
):
    with printer.dashboard.heartbeat(
        label,
        interval_seconds=interval_seconds,
        tty_dynamic=tty_dynamic,
        frames=frames,
    ) as handle:
        yield handle
