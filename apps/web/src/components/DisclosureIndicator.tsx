import { CaretDown } from '@phosphor-icons/react';

export function DisclosureIndicator() {
  return (
    <span className="disclosure-indicator" aria-hidden="true">
      <span className="disclosure-open-label">ОТКРЫТЬ</span>
      <span className="disclosure-close-label">СКРЫТЬ</span>
      <CaretDown weight="bold" />
    </span>
  );
}
