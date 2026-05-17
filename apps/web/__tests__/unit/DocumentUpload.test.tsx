import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentUpload } from '../../src/components/documents/DocumentUpload';

// jsdom does not implement crypto.randomUUID
let uuidCounter = 0;
Object.defineProperty(global, 'crypto', {
  value: { randomUUID: () => `mock-uuid-${++uuidCounter}` },
  configurable: true,
});

const mockShowToast = jest.fn();
jest.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

const mockUpload = jest.fn();
const mockFetchStatus = jest.fn();
jest.mock('@/lib/api/documents', () => ({
  uploadDocumentWithProgress: (...args: unknown[]) => mockUpload(...args),
  fetchDocumentStatus: (...args: unknown[]) => mockFetchStatus(...args),
  retryDocument: jest.fn(),
}));

function makeFile(name: string, type: string, sizeBytes = 1024): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: sizeBytes });
  return file;
}

describe('DocumentUpload', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders the drop zone and type selector', () => {
    render(<DocumentUpload courseId="c1" />);
    expect(screen.getByText(/Click to upload/)).toBeInTheDocument();
    expect(screen.getByText('Lecture')).toBeInTheDocument();
    expect(screen.getByText('Past Exam')).toBeInTheDocument();
    expect(screen.getByText('Supplement')).toBeInTheDocument();
  });

  it('rejects unsupported file types with a toast', () => {
    render(<DocumentUpload courseId="c1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = makeFile('notes.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    fireEvent.change(input, { target: { files: [file] } });
    expect(mockShowToast).toHaveBeenCalledWith('Unsupported format. Use PDF or PPTX.', 'err');
    expect(screen.queryByText('notes.docx')).not.toBeInTheDocument();
  });

  it('rejects files over 50 MB with a validation error row', () => {
    render(<DocumentUpload courseId="c1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const bigFile = makeFile('huge.pdf', 'application/pdf', 51 * 1024 * 1024);
    fireEvent.change(input, { target: { files: [bigFile] } });
    expect(screen.getByText('huge.pdf')).toBeInTheDocument();
    expect(screen.getByText('File too large (max 50 MB)')).toBeInTheDocument();
  });

  it('starts upload for valid PDF and shows uploading state', async () => {
    mockUpload.mockImplementation((_courseId, _file, _token, _type, onProgress) => {
      onProgress(50);
      return new Promise(() => {});
    });

    render(<DocumentUpload courseId="c1" accessToken="tok" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = makeFile('slides.pdf', 'application/pdf');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('slides.pdf')).toBeInTheDocument();
    });
    expect(mockUpload).toHaveBeenCalled();
  });

  it('shows "Indexed" status after successful upload and processing', async () => {
    mockUpload.mockResolvedValue({ id: 'doc-1' });
    mockFetchStatus.mockResolvedValue({ status: 'ready', processing_stage: 'done' });

    render(<DocumentUpload courseId="c1" accessToken="tok" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile('deck.pdf', 'application/pdf')] } });

    await waitFor(() => {
      expect(screen.getByText('Indexed')).toBeInTheDocument();
    });
  });

  it('changes selected type when type button is clicked', () => {
    render(<DocumentUpload courseId="c1" />);
    fireEvent.click(screen.getByText('Past Exam'));
    const pastExamBtn = screen.getByText('Past Exam').closest('button')!;
    expect(pastExamBtn.className).toMatch(/bg-blue-dark/);
  });
});
