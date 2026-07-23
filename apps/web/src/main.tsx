import { Buffer } from 'buffer';

globalThis.Buffer = Buffer;

const isControlSite =
  window.location.pathname === '/control' || window.location.pathname.startsWith('/control/');

if (isControlSite) {
  void import('./control/bootstrap');
} else {
  void import('./styles.css').then(() => import('./bootstrap'));
}
