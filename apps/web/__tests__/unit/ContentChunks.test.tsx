/**
 * The study content panel lists ready documents with their sample chunks, and
 * errored documents with their error, so a scanned PDF (#263) explains why it
 * has no content instead of silently disappearing.
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { ContentChunks } from '../../src/components/study/ContentChunks';

jest.mock('@/lib/services/documents', () => ({ getDocuments: jest.fn() }));
jest.mock('@/lib/api/documents', () => ({ getDocumentPreviewView: jest.fn() }));

import { getDocuments } from '@/lib/services/documents';
import { getDocumentPreviewView } from '@/lib/api/documents';

const mockGetDocuments = getDocuments as jest.Mock;
const mockGetPreview = getDocumentPreviewView as jest.Mock;

beforeEach(() => jest.clearAllMocks());

it('shows the error of a document that produced no text, without fetching its preview', async () => {
  mockGetDocuments.mockResolvedValue([
    {
      id: 'doc-scan',
      filename: 'scan.pdf',
      status: 'error',
      error_message: 'No searchable text was extracted from this document.',
    },
  ]);

  render(<ContentChunks courseId="c1" accessToken="t" />);

  expect(await screen.findByRole('alert')).toHaveTextContent('No searchable text was extracted');
  expect(screen.getByText('scan.pdf')).toBeInTheDocument();
  expect(mockGetPreview).not.toHaveBeenCalled();
});

it('shows sample chunks of a ready document and no alert', async () => {
  mockGetDocuments.mockResolvedValue([{ id: 'doc-1', filename: 'notes.pdf', status: 'ready' }]);
  mockGetPreview.mockResolvedValue({
    sections: ['Intro'],
    sampleChunks: [{ text: 'Bitcoin is a peer-to-peer cash system.', label: null, section: 'Intro' }],
  });

  render(<ContentChunks courseId="c1" accessToken="t" />);

  expect(await screen.findByText('Bitcoin is a peer-to-peer cash system.')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('skips documents that are still processing', async () => {
  mockGetDocuments.mockResolvedValue([
    { id: 'doc-p', filename: 'pending.pdf', status: 'processing' },
    { id: 'doc-e', filename: 'broken.pdf', status: 'error', error_message: 'Corrupt file' },
  ]);

  render(<ContentChunks courseId="c1" accessToken="t" />);

  expect(await screen.findByText('broken.pdf')).toBeInTheDocument();
  expect(screen.queryByText('pending.pdf')).not.toBeInTheDocument();
});
