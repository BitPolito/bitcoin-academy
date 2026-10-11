/**
 * A study result without citations means retrieval found no course passages;
 * the backend no longer generates in that case. The notice must say so instead
 * of claiming the retrieval service is down.
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { StudyOutput } from '../../src/components/study/StudyOutput';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));

describe('StudyOutput without evidence', () => {
  const noEvidence = {
    answer: 'No relevant content found.',
    citations: [],
    retrieval_used: false,
    action: 'explain' as const,
  };

  it('explains that no course passages matched and suggests a specific topic', () => {
    render(<StudyOutput result={noEvidence} courseId="course-1" />);

    expect(screen.getByText(/no passages from this course matched/i)).toBeInTheDocument();
    expect(screen.getByText(/specific concept, term or section/i)).toBeInTheDocument();
  });

  it('does not claim the retrieval service is unavailable', () => {
    render(<StudyOutput result={noEvidence} courseId="course-1" />);

    expect(screen.queryByText(/temporarily unavailable/i)).not.toBeInTheDocument();
  });
});
