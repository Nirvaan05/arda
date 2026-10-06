import subprocess, sys, pathlib
from playwright.sync_api import sync_playwright
import imageio_ffmpeg

HERE = pathlib.Path(__file__).parent
FPS, DUR = 30, 22.0
FF = imageio_ffmpeg.get_ffmpeg_exe()

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto((HERE / "video.html").as_uri())
    assert pg.evaluate("window.ready"), "fonts failed to load"
    if sys.argv[1:] and sys.argv[1] == "stills":  # python render.py stills 1.0 4.5 ...
        for t in sys.argv[2:]:
            pg.evaluate(f"render({t})")
            pg.screenshot(path=str(HERE / f"still_{t}.png"))
    else:
        out = sys.argv[1] if sys.argv[1:] else str(HERE / "video.mp4")
        ff = subprocess.Popen([FF, "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", out],
                              stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        for i in range(int(FPS * DUR)):
            pg.evaluate(f"render({i / FPS})")
            ff.stdin.write(pg.screenshot(type="png"))
        ff.stdin.close(); ff.wait()
    b.close()
