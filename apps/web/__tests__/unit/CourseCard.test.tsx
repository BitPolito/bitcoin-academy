import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { CourseCard } from '../../src/components/courses/CourseCard';

jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

const baseCourse = {
  id: 'btc-101',
  title: 'Bitcoin 101',
  description: 'Foundations of Bitcoin',
};

describe('CourseCard', () => {
  it('renders the course title in the heading', () => {
    render(<CourseCard course={baseCourse} />);
    expect(screen.getByRole('heading', { name: 'Bitcoin 101' })).toBeInTheDocument();
  });

  it('renders the course description', () => {
    render(<CourseCard course={baseCourse} />);
    expect(screen.getByText('Foundations of Bitcoin')).toBeInTheDocument();
  });

  it('links to the correct course URL', () => {
    render(<CourseCard course={baseCourse} />);
    expect(screen.getByRole('link')).toHaveAttribute('href', '/courses/btc-101');
  });

  it('shows "all indexed" status dot when all docs are indexed', () => {
    render(<CourseCard course={baseCourse} stats={{ total: 5, ready: 5, processing: 0, error: 0 }} />);
    expect(screen.getByText('all indexed')).toBeInTheDocument();
  });

  it('shows processing count when docs are processing', () => {
    render(<CourseCard course={baseCourse} stats={{ total: 5, ready: 3, processing: 2, error: 0 }} />);
    expect(screen.getByText('2 processing')).toBeInTheDocument();
  });

  it('shows failed count when docs have errors', () => {
    render(<CourseCard course={baseCourse} stats={{ total: 5, ready: 3, processing: 0, error: 2 }} />);
    expect(screen.getByText('2 failed')).toBeInTheDocument();
  });

  it('renders doc stats grid when stats are provided', () => {
    render(<CourseCard course={baseCourse} stats={{ total: 10, ready: 8, processing: 1, error: 1 }} />);
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
  });

  it('does not render stats grid when stats are null', () => {
    render(<CourseCard course={baseCourse} stats={null} />);
    expect(screen.queryByText('docs')).not.toBeInTheDocument();
  });

  it('snapshot: renders consistently', () => {
    const { container } = render(
      <CourseCard course={baseCourse} stats={{ total: 3, ready: 3, processing: 0, error: 0 }} />
    );
    expect(container).toMatchSnapshot();
  });
});
