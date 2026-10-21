import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { PdfPreview } from '@/components/documents/PdfPreview';
import { fetchDocumentPdf } from '@/lib/api/documents';

jest.mock('@/lib/api/documents', () => ({ fetchDocumentPdf: jest.fn() }));
const fetchPdf = fetchDocumentPdf as jest.MockedFunction<typeof fetchDocumentPdf>;
const createUrl = jest.fn(() => 'blob:local-pdf');
const revokeUrl = jest.fn();
const originalCreate = URL.createObjectURL;
const originalRevoke = URL.revokeObjectURL;
const pdf = new Blob(['%PDF-1.7'], { type: 'application/pdf' });

beforeAll(() => {
  URL.createObjectURL = createUrl;
  URL.revokeObjectURL = revokeUrl;
});
afterAll(() => {
  URL.createObjectURL = originalCreate;
  URL.revokeObjectURL = originalRevoke;
});
beforeEach(() => {
  jest.clearAllMocks();
  fetchPdf.mockReset();
  fetchPdf.mockResolvedValue(pdf);
});

it('loads with authentication, opens the cited page and changes pages without refetching', async () => {
  const view = render(<PdfPreview documentId="doc-1" accessToken="token" page={2} />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading PDF');
  expect(await screen.findByTitle('PDF viewer')).toHaveAttribute('src', 'blob:local-pdf#page=2');
  expect(fetchPdf).toHaveBeenCalledWith('doc-1', 'token', expect.any(AbortSignal));
  view.rerender(<PdfPreview documentId="doc-1" accessToken="token" page={4} />);
  expect(screen.getByTitle('PDF viewer')).toHaveAttribute('src', 'blob:local-pdf#page=4');
  expect(fetchPdf).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(revokeUrl).toHaveBeenCalledWith('blob:local-pdf');
});

it('shows the missing-file recovery message and can retry', async () => {
  fetchPdf.mockRejectedValueOnce(new Error('Original file is unavailable. Re-upload the document.'));
  render(<PdfPreview documentId="doc-1" accessToken="token" page={1} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Re-upload the document');
  expect(screen.queryByTitle('PDF viewer')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(await screen.findByTitle('PDF viewer')).toHaveAttribute('src', 'blob:local-pdf#page=1');
  expect(fetchPdf).toHaveBeenCalledTimes(2);
});

it('does not request a protected file without a session token', () => {
  render(<PdfPreview documentId="doc-1" page={1} />);
  expect(screen.getByRole('alert')).toHaveTextContent('Sign in');
  expect(fetchPdf).not.toHaveBeenCalled();
});

it('aborts pending work and ignores responses after unmount', async () => {
  let resolve!: (value: Blob) => void;
  fetchPdf.mockReturnValue(new Promise<Blob>((done) => { resolve = done; }));
  const view = render(<PdfPreview documentId="doc-1" accessToken="token" page={1} />);
  const signal = fetchPdf.mock.calls[0][2]!;
  view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => { resolve(pdf); });
  expect(createUrl).not.toHaveBeenCalled();
});

it('ignores stale results when switching documents', async () => {
  let resolveOld!: (value: Blob) => void;
  fetchPdf.mockReturnValueOnce(new Promise<Blob>((done) => { resolveOld = done; }));
  const view = render(<PdfPreview documentId="old" accessToken="token" page={1} />);
  const oldSignal = fetchPdf.mock.calls[0][2]!;
  view.rerender(<PdfPreview documentId="new" accessToken="token" page={3} />);
  expect(await screen.findByTitle('PDF viewer')).toHaveAttribute('src', 'blob:local-pdf#page=3');
  await act(async () => { resolveOld(pdf); });
  expect(oldSignal.aborted).toBe(true);
  expect(createUrl).toHaveBeenCalledTimes(1);
  expect(screen.getByTitle('PDF viewer')).toHaveAttribute('src', 'blob:local-pdf#page=3');
});

it('releases the loaded PDF when the session ends', async () => {
  const view = render(<PdfPreview documentId="doc-1" accessToken="token" page={1} />);
  await screen.findByTitle('PDF viewer');
  view.rerender(<PdfPreview documentId="doc-1" page={1} />);
  expect(screen.queryByTitle('PDF viewer')).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('Sign in');
  expect(revokeUrl).toHaveBeenCalledWith('blob:local-pdf');
});

it('cleans up correctly under StrictMode and normalizes invalid page values', async () => {
  const view = render(<StrictMode>
    <PdfPreview documentId="doc-1" accessToken="token" page={NaN} />
  </StrictMode>);
  expect(await screen.findByTitle('PDF viewer')).toHaveAttribute('src', 'blob:local-pdf#page=1');
  expect(createUrl).toHaveBeenCalledTimes(1);
  view.unmount();
  await waitFor(() => expect(revokeUrl).toHaveBeenCalledTimes(1));
});
