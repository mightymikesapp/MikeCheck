import { validateCitation } from './bluebook';
import { describe, it, expect } from 'vitest';

describe('Bluebook Validation Logic', () => {
  
  describe('Case Citations', () => {
    it('should validate correct case citations', () => {
      const result = validateCitation('Roe v. Wade, 410 U.S. 113 (1973)');
      expect(result.isValid).toBe(true);
      expect(result.type).toBe('case');
    });

    it('should detect invalid reporter spacing', () => {
      const result = validateCitation('Roe v. Wade, 410 U. S. 113 (1973)');
      expect(result.isValid).toBe(false);
      expect(result.issues).toContain("Check spacing in reporter abbreviation. Adjacent single capitals should be closed up (e.g., 'N.Y.' not 'N. Y.').");
      expect(result.corrected).toBe('Roe v. Wade, 410 U.S. 113 (1973)');
    });
  });

  describe('Legislative Materials', () => {
    it('should validate correct bill citations', () => {
      const result = validateCitation('H.R. 1234, 118th Cong. (2023)');
      expect(result.isValid).toBe(true);
      expect(result.type).toBe('legislative');
    });

    it('should validate correct report citations', () => {
      const result = validateCitation('H.R. Rep. No. 123-456 (2023)');
      expect(result.isValid).toBe(true);
      expect(result.type).toBe('legislative');
    });
  });

  describe('International Materials', () => {
    it('should validate correct treaty citations', () => {
      const result = validateCitation('Treaty Name, Jan. 1, 2020, U.S.-Fr., 123 U.N.T.S. 456');
      expect(result.isValid).toBe(true);
      expect(result.type).toBe('international');
    });
  });

  describe('Signal Capitalization', () => {
    it('should detect lowercase signals at start', () => {
      const result = validateCitation('see Roe v. Wade, 410 U.S. 113 (1973)');
      expect(result.isValid).toBe(false);
      expect(result.issues[0]).toContain("Signal 'See' should be capitalized");
      expect(result.corrected).toBe('See Roe v. Wade, 410 U.S. 113 (1973)');
    });

    it('should allow correct capitalized signals', () => {
      const result = validateCitation('See Roe v. Wade, 410 U.S. 113 (1973)');
      expect(result.isValid).toBe(true);
    });
  });

});
