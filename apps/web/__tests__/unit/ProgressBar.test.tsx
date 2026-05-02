import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { ProgressBar } from '../../src/components/ui/ProgressBar';

describe('ProgressBar', () => {
  describe('rendering', () => {
    it('renders a progressbar role element', () => {
      render(<ProgressBar percent={50} />);
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('shows the percentage label when showPercent is true (default)', () => {
      render(<ProgressBar percent={42} />);
      expect(screen.getByText('42%')).toBeInTheDocument();
    });

    it('hides the percentage label when showPercent is false', () => {
      render(<ProgressBar percent={42} showPercent={false} />);
      expect(screen.queryByText('42%')).not.toBeInTheDocument();
    });

    it('renders a custom label', () => {
      render(<ProgressBar percent={30} label="3 of 10 lessons completed" />);
      expect(screen.getByText('3 of 10 lessons completed')).toBeInTheDocument();
    });

    it('sets correct aria-valuenow', () => {
      render(<ProgressBar percent={75} />);
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '75');
    });

    it('sets aria-valuemin to 0 and aria-valuemax to 100', () => {
      render(<ProgressBar percent={50} />);
      const bar = screen.getByRole('progressbar');
      expect(bar).toHaveAttribute('aria-valuemin', '0');
      expect(bar).toHaveAttribute('aria-valuemax', '100');
    });
  });

  describe('value clamping', () => {
    it('clamps values above 100 to 100', () => {
      render(<ProgressBar percent={150} />);
      expect(screen.getByText('100%')).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    });

    it('clamps negative values to 0', () => {
      render(<ProgressBar percent={-20} />);
      expect(screen.getByText('0%')).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    });

    it('handles 0 correctly', () => {
      render(<ProgressBar percent={0} />);
      expect(screen.getByText('0%')).toBeInTheDocument();
    });

    it('handles 100 correctly', () => {
      render(<ProgressBar percent={100} />);
      expect(screen.getByText('100%')).toBeInTheDocument();
    });
  });

  describe('bar width', () => {
    it('sets the inner bar width to the given percent', () => {
      const { container } = render(<ProgressBar percent={60} />);
      const inner = container.querySelector('[style]') as HTMLElement;
      expect(inner?.style.width).toBe('60%');
    });

    it('uses green color at 100%', () => {
      const { container } = render(<ProgressBar percent={100} />);
      const inner = container.querySelector('[style]') as HTMLElement;
      expect(inner?.className).toContain('bg-green-500');
    });

    it('uses orange color below 100%', () => {
      const { container } = render(<ProgressBar percent={50} />);
      const inner = container.querySelector('[style]') as HTMLElement;
      expect(inner?.className).toContain('bg-orange-500');
    });
  });
});
