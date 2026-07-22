export function installInteractionGuards(): () => void {
  const prevent = (event: Event) => event.preventDefault();
  const preventKeyboardZoom = (event: KeyboardEvent) => {
    if ((event.ctrlKey || event.metaKey) && ['+', '-', '=', '0'].includes(event.key)) {
      event.preventDefault();
    }
  };
  const preventWheelZoom = (event: WheelEvent) => {
    if (event.ctrlKey) event.preventDefault();
  };

  document.addEventListener('selectstart', prevent);
  document.addEventListener('contextmenu', prevent);
  document.addEventListener('dragstart', prevent);
  document.addEventListener('gesturestart', prevent, { passive: false });
  document.addEventListener('gesturechange', prevent, { passive: false });
  document.addEventListener('gestureend', prevent, { passive: false });
  document.addEventListener('wheel', preventWheelZoom, { passive: false });
  window.addEventListener('keydown', preventKeyboardZoom);

  return () => {
    document.removeEventListener('selectstart', prevent);
    document.removeEventListener('contextmenu', prevent);
    document.removeEventListener('dragstart', prevent);
    document.removeEventListener('gesturestart', prevent);
    document.removeEventListener('gesturechange', prevent);
    document.removeEventListener('gestureend', prevent);
    document.removeEventListener('wheel', preventWheelZoom);
    window.removeEventListener('keydown', preventKeyboardZoom);
  };
}
