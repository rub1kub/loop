import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Loader } from './Loader';

describe('Loader', () => {
  it('has an accessible loading label and no distracting copy', () => {
    render(<Loader />);
    expect(screen.getByLabelText('LOOP загружается')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });
});
