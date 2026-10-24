// The time left to press Keep these settings, counted down while the page is open. Without
// JavaScript the box shows the time left when the page was opened.
const timer = document.querySelector(".keep-bar [data-left]");
if (timer) {
  const end = Date.now() + Number(timer.dataset.left) * 1000;
  const tick = () => {
    const left = Math.max(0, Math.round((end - Date.now()) / 1000));
    timer.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    if (left > 0) setTimeout(tick, 1000);
    // PaperPi went back by itself: open the old address once it listens there.
    else if (timer.dataset.old) setTimeout(() => location.assign(timer.dataset.old), 5000);
  };
  tick();
}
