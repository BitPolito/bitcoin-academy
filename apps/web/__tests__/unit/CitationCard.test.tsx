import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { CitationCard } from '../../src/components/study/CitationCard';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const baseCitation = {
  snippet: 'A UTXO is an unspent transaction output.',
  score: 0.88,
  label: 'lecture01.pdf',
  page: 7,
  slide: 0,
  section: 'Bitcoin Basics',
  doc_id: 'doc-abc',
};

describe('CitationCard', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders the snippet text', () => {
    render(<CitationCard citation={baseCitation} courseId="c1" index={1} />);
    expect(screen.getByText(/UTXO is an unspent/)).toBeInTheDocument();
  });

  it('renders the relevance percentage', () => {
    render(<CitationCard citation={baseCitation} courseId="c1" index={1} />);
    expect(screen.getByText('88%')).toBeInTheDocument();
  });

  it('renders the document label and page', () => {
    render(<CitationCard citation={baseCitation} courseId="c1" index={1} />);
    expect(screen.getByText(/lecture01\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/p\.7/)).toBeInTheDocument();
  });

  it('renders the section when present', () => {
    render(<CitationCard citation={baseCitation} courseId="c1" index={1} />);
    expect(screen.getByText('Bitcoin Basics')).toBeInTheDocument();
  });

  it('shows "View in source →" link when doc_id is present', () => {
    render(<CitationCard citation={baseCitation} courseId="c1" index={1} />);
    expect(screen.getByText(/View in source/)).toBeInTheDocument();
  });

  it('navigates to the document preview on click', () => {
    render(<CitationCard citation={baseCitation} courseId="c1" index={1} />);
    fireEvent.click(screen.getByText(/View in source/).closest('div')!);
    expect(mockPush).toHaveBeenCalledWith(
      '/courses/c1/documents/doc-abc/preview?page=7'
    );
  });

  it('uses slide parameter in URL when only slide is set', () => {
    const citation = { ...baseCitation, page: 0, slide: 3 };
    render(<CitationCard citation={citation} courseId="c2" index={2} />);
    fireEvent.click(screen.getByText(/View in source/).closest('div')!);
    expect(mockPush).toHaveBeenCalledWith(
      '/courses/c2/documents/doc-abc/preview?slide=3'
    );
  });

  it('does not navigate when doc_id is empty', () => {
    const citation = { ...baseCitation, doc_id: '' };
    render(<CitationCard citation={citation} courseId="c1" index={1} />);
    // No "View in source" link and no onClick — clicking the snippet p does nothing
    fireEvent.click(screen.getByText(/UTXO/).closest('p')!);
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('truncates long snippets to 180 chars', () => {
    const longSnippet = 'x'.repeat(200);
    render(<CitationCard citation={{ ...baseCitation, snippet: longSnippet }} courseId="c1" index={1} />);
    expect(screen.getByText(/x{1,180}…/)).toBeInTheDocument();
  });

  it('renders "Source" as fallback label when label and location are empty', () => {
    const citation = { ...baseCitation, label: '', page: 0, slide: 0 };
    render(<CitationCard citation={citation} courseId="c1" index={1} />);
    expect(screen.getByText(/\[1\] Source/i)).toBeInTheDocument();
  });
});
