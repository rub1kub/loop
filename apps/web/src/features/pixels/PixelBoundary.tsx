import { Component, type ReactNode } from 'react';

/** Canvas support or a pixel-only render error must never take down the Mini App. */
export class PixelBoundary extends Component<
  {
    children: ReactNode;
    onClose: () => void;
  },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onClose();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}
