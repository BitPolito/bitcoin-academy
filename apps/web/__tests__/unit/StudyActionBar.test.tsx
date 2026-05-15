import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { StudyActionBar } from '../../src/components/study/StudyActionBar';

describe('StudyActionBar', () => {
  const noop = jest.fn();

  beforeEach(() => jest.clearAllMocks());

  it('renders all 8 action buttons', () => {
    render(<StudyActionBar onAction={noop} activeAction={null} loading={false} />);
    const labels = ['Explain', 'Summarize', 'Retrieve', 'Questions', 'Quiz', 'Oral Exam', 'Derive', 'Compare'];
    for (const label of labels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('calls onAction with the correct id when a button is clicked', () => {
    render(<StudyActionBar onAction={noop} activeAction={null} loading={false} />);
    fireEvent.click(screen.getByText('Explain').closest('button')!);
    expect(noop).toHaveBeenCalledWith('explain');
  });

  it('disables all buttons while loading', () => {
    render(<StudyActionBar onAction={noop} activeAction={null} loading={true} />);
    const buttons = screen.getAllByRole('button');
    for (const btn of buttons) {
      expect(btn).toBeDisabled();
    }
  });

  it('disables all buttons when disabled prop is true', () => {
    render(<StudyActionBar onAction={noop} activeAction={null} loading={false} disabled />);
    const buttons = screen.getAllByRole('button');
    for (const btn of buttons) {
      expect(btn).toBeDisabled();
    }
  });

  it('disables all buttons when hasIndexedDocs is false', () => {
    render(<StudyActionBar onAction={noop} activeAction={null} loading={false} hasIndexedDocs={false} />);
    const buttons = screen.getAllByRole('button');
    for (const btn of buttons) {
      expect(btn).toBeDisabled();
    }
  });

  it('shows "Upload documents first" tooltip when hasIndexedDocs is false', () => {
    render(<StudyActionBar onAction={noop} activeAction={null} loading={false} hasIndexedDocs={false} />);
    const buttons = screen.getAllByRole('button');
    for (const btn of buttons) {
      expect(btn).toHaveAttribute('title', 'Upload documents first');
    }
  });

  it('applies active styling to the active action button', () => {
    render(<StudyActionBar onAction={noop} activeAction="quiz" loading={false} />);
    const quizBtn = screen.getByText('Quiz').closest('button')!;
    expect(quizBtn.className).toMatch(/bg-blue-dark/);
  });

  it('does not apply active styling to inactive buttons', () => {
    render(<StudyActionBar onAction={noop} activeAction="quiz" loading={false} />);
    const explainBtn = screen.getByText('Explain').closest('button')!;
    expect(explainBtn.className).not.toMatch(/bg-blue-dark text-white/);
  });
});
