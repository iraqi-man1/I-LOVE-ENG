"""The interface builds every screen without errors (runs offscreen)."""

import os

import pytest

os.environ.setdefault("PDFTOOLBOX_FAKE_SCANNER", "1")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    from pdftoolbox.ui import theme

    application = QApplication.instance() or QApplication([])
    theme.apply(application, "light")
    yield application


def pump(ms=100):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_every_tool_page_opens(app, make_pdf, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from pdftoolbox.tools import all_tools
    from pdftoolbox.ui.main_window import MainWindow

    pdf = make_pdf(pages=2)
    win = MainWindow()
    win.show()
    for tool in all_tools():
        if tool.hidden:
            continue
        win.open_tool(tool.id, [str(pdf)] if tool.accepts(str(pdf)) else [])
        page = win.pages[tool.id]
        values = page.form.values()
        assert set(values) == {o.key for o in tool.options}
    win.open_tool("__scan__")
    pump(800)
    win.close()


def test_run_job_from_page(app, make_pdf, tmp_path):
    from pdftoolbox.ui.main_window import MainWindow

    a, b = make_pdf(pages=1), make_pdf(pages=2)
    win = MainWindow()
    win.open_tool("merge", [str(a), str(b)])
    page = win.pages["merge"]
    page.name_edit.setText("joined")
    page.start()
    for _ in range(300):
        pump(100)
        if not page.runner.running:
            break
    assert not page.results_box.isHidden()
    assert "✓" in page.results_title.text()
    assert (a.parent / "joined.pdf").exists()
    win.close()


def test_quitting_during_update_check_is_safe(app, monkeypatch):
    # The check is still waiting on the network when the tests finish. With a
    # QThread this aborted the whole process at exit.
    import threading
    import time

    from pdftoolbox.ui.main_window import MainWindow
    from pdftoolbox.updater import github

    started = threading.Event()

    def slow_check(*args, **kwargs):
        started.set()
        time.sleep(60)

    monkeypatch.setattr(github, "check_latest", slow_check)
    win = MainWindow()
    win.check_updates(manual=False)
    assert started.wait(5)
    win.close()


def test_home_search_and_drop_filter(app, make_pdf):
    from pdftoolbox.ui.main_window import HomePage

    home = HomePage()
    home.search.setText("password")
    visible = [c.tool_id for _, _, cards in home.sections for c in cards if not c.isHidden()]
    assert "protect" in visible and "merge" not in visible
    home.search.clear()
    home.pending = ["/tmp/photo.jpg"]
    home.refilter()
    visible = [c.tool_id for _, _, cards in home.sections for c in cards if not c.isHidden()]
    assert visible == ["image_to_pdf"]
