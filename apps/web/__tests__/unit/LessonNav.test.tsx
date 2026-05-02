import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { LessonNav } from '../../src/components/study/LessonNav';
import type { Lesson } from '../../src/lib/services/courses';

const LESSONS: Lesson[] = [
  { id: 1, title: 'Introduction to Bitcoin' },
  { id: 2, title: 'How Mining Works' },
  { id: 3, title: 'Lightning Network' },
];

describe('LessonNav', () => {
  const noop = () => {};

  describe('rendering', () => {
    it('renders all lesson titles', () => {
      render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={null}
          completedLessons={new Set()}
          onSelect={noop}
        />
      );

      expect(screen.getByText('Introduction to Bitcoin')).toBeInTheDocument();
      expect(screen.getByText('How Mining Works')).toBeInTheDocument();
      expect(screen.getByText('Lightning Network')).toBeInTheDocument();
    });

    it('renders 1-based ordinal numbers for each lesson', () => {
      render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={null}
          completedLessons={new Set()}
          onSelect={noop}
        />
      );

      expect(screen.getByText('1')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });

    it('shows empty state when lessons array is empty', () => {
      render(
        <LessonNav
          lessons={[]}
          selectedLesson={null}
          completedLessons={new Set()}
          onSelect={noop}
        />
      );

      expect(screen.getByText(/no lessons available/i)).toBeInTheDocument();
    });

    it('shows loading skeleton when loading is true', () => {
      const { container } = render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={null}
          completedLessons={new Set()}
          onSelect={noop}
          loading
        />
      );

      // Skeleton divs are present; lesson titles are not rendered
      expect(screen.queryByText('Introduction to Bitcoin')).not.toBeInTheDocument();
      expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
    });
  });

  describe('selection', () => {
    it('marks the selected lesson with aria-current', () => {
      render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={LESSONS[1]}
          completedLessons={new Set()}
          onSelect={noop}
        />
      );

      const buttons = screen.getAllByRole('button');
      expect(buttons[1]).toHaveAttribute('aria-current', 'true');
      expect(buttons[0]).not.toHaveAttribute('aria-current');
    });

    it('calls onSelect with the clicked lesson', () => {
      const onSelect = jest.fn();
      render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={null}
          completedLessons={new Set()}
          onSelect={onSelect}
        />
      );

      fireEvent.click(screen.getByText('How Mining Works'));
      expect(onSelect).toHaveBeenCalledWith(LESSONS[1]);
    });
  });

  describe('completion state', () => {
    it('shows "Done" label for completed lessons', () => {
      render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={null}
          completedLessons={new Set(['1', '3'])}
          onSelect={noop}
        />
      );

      // Two lessons are done
      expect(screen.getAllByText('Done')).toHaveLength(2);
    });

    it('does not show "Done" for incomplete lessons', () => {
      render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={null}
          completedLessons={new Set(['1'])}
          onSelect={noop}
        />
      );

      expect(screen.getAllByText('Done')).toHaveLength(1);
    });

    it('hides the ordinal number for completed lessons (replaced by checkmark)', () => {
      render(
        <LessonNav
          lessons={LESSONS}
          selectedLesson={null}
          completedLessons={new Set(['1'])}
          onSelect={noop}
        />
      );

      // Lesson 1 is complete: no "1" badge visible, but "2" and "3" are
      expect(screen.queryByText('1')).not.toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });
  });
});
