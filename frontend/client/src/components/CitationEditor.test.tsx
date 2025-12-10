import { render, screen, fireEvent } from '@testing-library/react';
import CitationEditor from './CitationEditor';
import { describe, it, expect, vi } from 'vitest';
import * as matchers from '@testing-library/jest-dom/matchers';

expect.extend(matchers);

// Mock the bluebook library since we tested it separately
vi.mock('@/lib/bluebook', () => ({
  validateCitation: vi.fn((text) => {
    if (text.includes('see')) {
      return {
        isValid: false,
        issues: ["Signal 'See' should be capitalized"],
        corrected: text.replace('see', 'See'),
        type: 'case'
      };
    }
    return { isValid: true, issues: [], type: 'case' };
  })
}));

describe('CitationEditor Component', () => {
  it('renders the editor textarea', () => {
    render(<CitationEditor />);
    expect(screen.getByPlaceholderText(/Type your citations here/i)).toBeInTheDocument();
  });

  it('shows validation results when typing', () => {
    render(<CitationEditor />);
    const textarea = screen.getByPlaceholderText(/Type your citations here/i);
    
    fireEvent.change(textarea, { target: { value: 'Roe v. Wade, 410 U.S. 113 (1973)' } });
    
    // Should show valid result - check for the specific badge
    const validBadges = screen.getAllByText(/Valid/i);
    expect(validBadges.length).toBeGreaterThan(0);
    expect(validBadges[0]).toBeInTheDocument();
  });

  it('shows fix it button for errors', () => {
    render(<CitationEditor />);
    const textarea = screen.getByPlaceholderText(/Type your citations here/i);
    
    fireEvent.change(textarea, { target: { value: 'see Roe v. Wade, 410 U.S. 113 (1973)' } });
    
    // Should show error and fix button
    expect(screen.getByText(/Issues Found/i)).toBeInTheDocument();
    expect(screen.getByText(/Fix It:/i)).toBeInTheDocument();
  });

  it('applies corrections when clicking Fix It', async () => {
    render(<CitationEditor />);
    const textarea = screen.getByPlaceholderText(/Type your citations here/i) as HTMLTextAreaElement;

    const invalidText = 'see Roe v. Wade, 410 U.S. 113 (1973)';
    const correctedText = 'See Roe v. Wade, 410 U.S. 113 (1973)';

    fireEvent.change(textarea, { target: { value: invalidText } });

    const fixButton = await screen.findByRole('button', { name: `Fix It: ${correctedText}` });
    fireEvent.click(fixButton);

    expect(textarea.value).toBe(correctedText);
  });
});
