/* Native, interruptible motion. No routing or API ownership lives here. */
(() => {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const animations = new Set();
  const animate = (element, frames, options) => {
    if (reducedMotion.matches || !element.animate) return;
    const animation = element.animate(frames, { duration: 420, easing: 'cubic-bezier(.22,1,.36,1)', ...options });
    animations.add(animation);
    animation.finished.catch(() => {}).finally(() => animations.delete(animation));
  };
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) animations.forEach(animation => animation.cancel());
  });
  window.MailroomMotion = {
    positions: container => new Map([...container.children].map(node => [node.dataset.case, node.getBoundingClientRect()])),
    reveal(container, previous = new Map()) {
      [...container.children].slice(0, 24).forEach((node, index) => {
        const before = previous?.get(node.dataset.case);
        const after = node.getBoundingClientRect();
        if (after.top > innerHeight) return;
        const offset = before ? Math.max(-60, Math.min(60, before.top - after.top)) : 8;
        animate(node, [{ opacity: before ? 1 : 0, transform: `translateY(${offset}px)` }, { opacity: 1, transform: 'none' }], { delay: before ? 0 : Math.min(index * 18, 126) });
      });
    }
  };
  // The shell renders after API hydration; delegation also covers new controls.
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      const search = document.getElementById('globalSearch');
      if (search) { event.preventDefault(); search.focus(); }
    }
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-filter]');
    if (button) animate(button, [{ transform: 'scale(.96)' }, { transform: 'scale(1.012)', offset: .7 }, { transform: 'scale(1)' }]);
  });
})();
