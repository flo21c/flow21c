"""창으로 쓰는 kakaosum.

파일을 고르고 버튼을 누르면 요약을 만들어 보여 준다. 윈도우에서 만든
``kakaosum.exe`` 를 더블클릭하면 이 창이 열리고, 대화 .txt 파일을 exe 위로
끌어다 놓으면 그 파일이 바로 열린다.

tkinter 는 함수 안에서 불러온다. 창을 띄우지 않는 환경(서버 등)에서도
이 모듈을 import 할 수 있게 하기 위해서다.
"""

from __future__ import annotations

import queue
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from .parser import ParseError, parse_file
from .render import render
from .summarize import summarize

WINDOW_TITLE = "kakaosum — 카카오톡 대화 요약기"
PERIOD_CHOICES = (("전체 기간", 0), ("최근 7일", 7), ("최근 30일", 30), ("최근 90일", 90))
GROUP_CHOICES = (("날짜별로", "day"), ("대화 덩어리별로", "session"), ("나누지 않기", "none"))


@dataclass
class Options:
    """창에서 고른 값들."""

    last_days: int = 0
    group: str = "day"
    mask: bool = False
    redact: bool = False
    no_system: bool = False
    fmt: str = "markdown"


def build_summary(path: str | Path, options: Options) -> str:
    """파일 하나를 읽어 요약 글을 만든다. (창 없이도 동작하는 부분)"""
    log = parse_file(path)
    if options.no_system:
        log = log.filtered(include_system=False)
    if options.last_days:
        log = log.last_days(options.last_days)
    if options.mask:
        log = log.masked()
    if not log.messages:
        raise ParseError("고른 기간에 해당하는 메시지가 없습니다.")
    summary = summarize(log, group=options.group)
    return render(summary, options.fmt, redact=options.redact)


def suggested_output(path: str | Path, fmt: str = "markdown") -> Path:
    """저장 창에 미리 채워 넣을 파일 이름."""
    source = Path(path)
    suffix = {"markdown": ".md", "text": ".txt", "json": ".json"}.get(fmt, ".md")
    return source.with_name(f"{source.stem}_요약{suffix}")


class App:
    """요약 창."""

    def __init__(self, master, initial_file: str | None = None) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.master = master
        self.result_queue: queue.Queue = queue.Queue()
        self.source_path: Path | None = None
        self.result_text: str = ""
        self.working = False

        master.title(WINDOW_TITLE)
        master.geometry("900x680")
        master.minsize(720, 520)

        self.file_var = tk.StringVar(value="대화 파일을 선택해 주세요")
        self.period_var = tk.StringVar(value=PERIOD_CHOICES[0][0])
        self.group_var = tk.StringVar(value=GROUP_CHOICES[0][0])
        self.format_var = tk.StringVar(value="마크다운 (.md)")
        self.mask_var = tk.BooleanVar(value=False)
        self.redact_var = tk.BooleanVar(value=False)
        self.system_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="준비됐습니다.")

        outer = ttk.Frame(master, padding=12)
        outer.pack(fill="both", expand=True)

        # 1) 파일 고르기
        picker = ttk.LabelFrame(outer, text="1. 대화 파일", padding=10)
        picker.pack(fill="x")
        ttk.Button(picker, text="파일 선택…", command=self.choose_file).pack(side="left")
        ttk.Label(picker, textvariable=self.file_var).pack(side="left", padx=10)

        # 2) 옵션
        options = ttk.LabelFrame(outer, text="2. 옵션", padding=10)
        options.pack(fill="x", pady=(10, 0))

        row = ttk.Frame(options)
        row.pack(fill="x")
        ttk.Label(row, text="기간").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.period_var,
            values=[label for label, _ in PERIOD_CHOICES],
            state="readonly",
            width=12,
        ).pack(side="left", padx=(6, 18))
        ttk.Label(row, text="정리 방식").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.group_var,
            values=[label for label, _ in GROUP_CHOICES],
            state="readonly",
            width=16,
        ).pack(side="left", padx=(6, 18))
        ttk.Label(row, text="형식").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.format_var,
            values=["마크다운 (.md)", "텍스트 (.txt)", "JSON (.json)"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=6)

        checks = ttk.Frame(options)
        checks.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(checks, text="이름 가리기 (참여자 A)", variable=self.mask_var).pack(side="left")
        ttk.Checkbutton(checks, text="전화번호·이메일 가리기", variable=self.redact_var).pack(
            side="left", padx=14
        )
        ttk.Checkbutton(checks, text="입·퇴장 알림 빼기", variable=self.system_var).pack(side="left")

        # 3) 실행
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=10)
        self.run_button = ttk.Button(actions, text="요약 만들기", command=self.run)
        self.run_button.pack(side="left")
        self.save_button = ttk.Button(actions, text="저장…", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        self.copy_button = ttk.Button(actions, text="복사", command=self.copy, state="disabled")
        self.copy_button.pack(side="left")

        # 4) 결과
        result = ttk.LabelFrame(outer, text="3. 결과", padding=6)
        result.pack(fill="both", expand=True)
        self.text = tk.Text(result, wrap="word", undo=False)
        scroll = ttk.Scrollbar(result, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for family in ("맑은 고딕", "Malgun Gothic", "AppleGothic", "NanumGothic"):
            try:
                self.text.configure(font=(family, 10))
                break
            except self.tk.TclError:  # pragma: no cover - 폰트가 없는 환경
                continue

        ttk.Label(outer, textvariable=self.status_var, foreground="#666").pack(
            fill="x", pady=(8, 0)
        )

        if initial_file:
            self.set_file(Path(initial_file))

    # -- 동작 ---------------------------------------------------------------
    def options(self) -> Options:
        periods = dict(PERIOD_CHOICES)
        groups = dict(GROUP_CHOICES)
        formats = {"마크다운 (.md)": "markdown", "텍스트 (.txt)": "text", "JSON (.json)": "json"}
        return Options(
            last_days=periods.get(self.period_var.get(), 0),
            group=groups.get(self.group_var.get(), "day"),
            mask=self.mask_var.get(),
            redact=self.redact_var.get(),
            no_system=self.system_var.get(),
            fmt=formats.get(self.format_var.get(), "markdown"),
        )

    def set_file(self, path: Path) -> None:
        self.source_path = path
        self.file_var.set(str(path))
        self.status_var.set("'요약 만들기' 를 눌러 주세요.")

    def choose_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="카카오톡 대화 파일 고르기",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
        )
        if path:
            self.set_file(Path(path))

    def run(self) -> None:
        if self.working:
            return
        if not self.source_path:
            self.status_var.set("먼저 대화 파일을 선택해 주세요.")
            return

        self.working = True
        self.run_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.status_var.set("요약하는 중…")

        path, options = self.source_path, self.options()

        def work() -> None:
            try:
                self.result_queue.put(("ok", build_summary(path, options)))
            except Exception as exc:  # 창이 그냥 닫히지 않도록 모든 오류를 받는다
                self.result_queue.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self.master.after(100, self.poll)

    def poll(self) -> None:
        try:
            kind, payload = self.result_queue.get_nowait()
        except queue.Empty:
            self.master.after(100, self.poll)
            return

        self.working = False
        self.run_button.configure(state="normal")
        if kind == "ok":
            self.result_text = payload
            self.text.delete("1.0", "end")
            self.text.insert("1.0", payload)
            self.save_button.configure(state="normal")
            self.copy_button.configure(state="normal")
            self.status_var.set("요약을 만들었습니다. '저장…' 으로 파일에 담을 수 있습니다.")
        else:
            self.result_text = ""
            self.text.delete("1.0", "end")
            self.text.insert("1.0", f"요약하지 못했습니다.\n\n{payload}")
            self.status_var.set("실패했습니다.")

    def save(self) -> None:
        from tkinter import filedialog, messagebox

        if not self.result_text or not self.source_path:
            return
        fmt = self.options().fmt
        default = suggested_output(self.source_path, fmt)
        path = filedialog.asksaveasfilename(
            title="요약 저장",
            initialfile=default.name,
            initialdir=str(default.parent),
            defaultextension=default.suffix,
        )
        if not path:
            return
        try:
            Path(path).write_text(self.result_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))
            return
        self.status_var.set(f"저장했습니다: {path}")

    def copy(self) -> None:
        if not self.result_text:
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(self.result_text)
        self.status_var.set("클립보드에 복사했습니다.")


def main(argv: list[str] | None = None) -> int:
    """창을 띄운다. 인자로 받은 파일이 있으면 미리 채워 넣는다."""
    args = list(sys.argv[1:] if argv is None else argv)
    initial = next((a for a in args if not a.startswith("-")), None)

    try:
        import tkinter as tk
    except ImportError:
        print(
            "창 모드를 쓰려면 tkinter 가 필요합니다. 명령줄에서 'kakaosum summarize 파일.txt' 를 쓰세요.",
            file=sys.stderr,
        )
        return 1

    root = tk.Tk()
    App(root, initial_file=initial)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
