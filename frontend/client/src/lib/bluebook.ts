/**
 * Bluebook Citation Validator
 * 
 * This module provides validation logic for legal citations based on The Bluebook: A Uniform System of Citation.
 * It checks for common formatting errors in case names, reporters, signals, and parentheticals.
 */

export interface ValidationResult {
  isValid: boolean;
  issues: string[];
  corrected?: string;
  type: 'case' | 'statute' | 'journal' | 'legislative' | 'international' | 'unknown';
}

// Regex patterns for common citation components
const PATTERNS = {
  // Basic case citation: Name, Vol Reporter Page (Year)
  CASE_CITATION: /^([^,]+),\s+(\d+)\s+([A-Za-z0-9\.\s]+)\s+(\d+)\s+\((\d{4})\)$/,
  
  // Legislative Materials (Rule 13)
  // Bills: H.R. 1234, 118th Cong. (2023)
  BILL_CITATION: /^(H\.R\.|S\.)\s+(\d+),\s+(\d+)(st|nd|rd|th)\s+Cong\.\s+\((\d{4})\)$/,
  // Hearings: Title, Cong., at Page (Year)
  HEARING_CITATION: /^(.+),\s+(\d+)(st|nd|rd|th)\s+Cong\.\s+(.+)\s+\((\d{4})\)$/,
  // Reports: H.R. Rep. No. 123-456 (2023)
  REPORT_CITATION: /^(H\.R\.|S\.)\s+Rep\.\s+No\.\s+(\d+)-(\d+)\s+\((\d{4})\)$/,

  // International Materials (Rule 21)
  // Treaties: Name, Date, Parties, Vol Source Page
  TREATY_CITATION: /^(.+),\s+([A-Za-z]+\.?\s+\d{1,2},\s+\d{4}),\s+(.+),\s+(\d+)\s+([A-Za-z\.\s]+)\s+(\d+)$/,
  // UN Documents: Title, Res. No., UN Doc. ID (Date)
  UN_DOC_CITATION: /^(.+),\s+([A-Za-z\.\s]+\d+),\s+U\.N\.\s+Doc\.\s+([A-Za-z0-9\/\.]+)\s+\(([A-Za-z]+\.?\s+\d{1,2},\s+\d{4})\)$/,

  // Reporter abbreviations (simplified list)
  REPORTERS: [
    'U.S.', 'S. Ct.', 'L. Ed.', 'F.', 'F.2d', 'F.3d', 'F. Supp.', 'F. Supp. 2d',
    'Cal.', 'Cal. 2d', 'Cal. 3d', 'Cal. 4th', 'N.Y.', 'N.Y.2d', 'N.Y.3d'
  ],
  
  // Signals
  SIGNALS: [
    'See', 'See also', 'E.g.', 'Accord', 'See, e.g.', 'Cf.', 'Compare', 'with',
    'But see', 'But cf.', 'Contra'
  ]
};

export function validateCitation(text: string): ValidationResult {
  const issues: string[] = [];
  let type: ValidationResult['type'] = 'unknown';
  
  // Clean input
  const cleanText = text.trim();
  
  // Check 1: Case Citation Format
  if (cleanText.match(PATTERNS.CASE_CITATION)) {
    type = 'case';
    validateCaseCitation(cleanText, issues);
  } 
  // Check 2: Statute Citation Format
  else if (cleanText.includes('U.S.C.')) {
    type = 'statute';
    if (!cleanText.match(/^\d+\s+U\.S\.C\.\s+§\s+\d+(\s+\(\d{4}\))?$/)) {
      issues.push("Statute citation format should be: Vol U.S.C. § Sec (Year)");
    }
  }
  // Check 3: Legislative Materials
  else if (cleanText.match(PATTERNS.BILL_CITATION)) {
    type = 'legislative';
    // Valid bill format
  } else if (cleanText.match(PATTERNS.REPORT_CITATION)) {
    type = 'legislative';
    // Valid report format
  } else if (cleanText.startsWith('H.R.') || cleanText.startsWith('S.')) {
    type = 'legislative';
    issues.push("Legislative citation format appears incorrect. Check Rule 13 (e.g., H.R. 1234, 118th Cong. (2023)).");
  }
  // Check 4: International Materials
  else if (cleanText.match(PATTERNS.TREATY_CITATION)) {
    type = 'international';
    // Valid treaty format
  } else if (cleanText.match(PATTERNS.UN_DOC_CITATION)) {
    type = 'international';
    // Valid UN doc format
  } else if (cleanText.includes('U.N. Doc.') || cleanText.includes('U.N.T.S.')) {
    type = 'international';
    issues.push("International citation format appears incorrect. Check Rule 21.");
  }
  else {
    // Fallback heuristic
    if (cleanText.match(/\d+\s+[A-Za-z\.]+\s+\d+/)) {
      type = 'case';
      issues.push("Citation format appears incorrect. Standard format: Case Name, Vol Reporter Page (Year)");
    }
  }

  // Check 5: Spacing in Reporters
  // Bluebook Rule 6.1: Close up adjacent single capitals (N.Y., not N. Y.)
  if (cleanText.match(/[A-Z]\.\s+[A-Z]\./)) {
    issues.push("Check spacing in reporter abbreviation. Adjacent single capitals should be closed up (e.g., 'N.Y.' not 'N. Y.').");
    // Generate correction
    const corrected = cleanText.replace(/([A-Z]\.)\s+([A-Z]\.)/g, '$1$2');
    return {
      isValid: false,
      issues,
      corrected,
      type
    };
  }

  // Check 6: Signals
  const signalMatch = cleanText.match(/^([A-Za-z,\.\s]+)/);
  if (signalMatch) {
    const potentialSignal = signalMatch[1].trim();
    
    // Check for lowercase signals at start of citation (should be capitalized)
    const lowerSignal = potentialSignal.toLowerCase();
    const matchedSignal = PATTERNS.SIGNALS.find(s => lowerSignal.startsWith(s.toLowerCase()));
    
    if (matchedSignal) {
      // Check capitalization
      if (potentialSignal.charAt(0) !== matchedSignal.charAt(0)) {
        issues.push(`Signal '${matchedSignal}' should be capitalized at the start of a citation sentence.`);
        const corrected = cleanText.replace(potentialSignal, matchedSignal + potentialSignal.slice(matchedSignal.length));
        return {
          isValid: false,
          issues,
          corrected,
          type
        };
      }
    }
  }

  return {
    isValid: issues.length === 0,
    issues,
    type
  };
}

function validateCaseCitation(text: string, issues: string[]) {
  const match = text.match(PATTERNS.CASE_CITATION);
  if (!match) return;

  const [_, name, vol, reporter, page, year] = match;

  // Check Year
  const yearNum = parseInt(year);
  const currentYear = new Date().getFullYear();
  if (yearNum < 1750 || yearNum > currentYear) {
    issues.push(`Year ${year} seems invalid for a case citation.`);
  }

  // Check Reporter
  // This is a basic check; a full implementation would check against a comprehensive list
  if (reporter.endsWith('..')) {
    issues.push("Reporter abbreviation has double periods.");
  }
  
  // Check Case Name
  if (name.endsWith(',')) {
    issues.push("Case name should not end with a comma inside the italicized portion (logic depends on parsing).");
  }
}

export function parseFootnotes(text: string): Array<{id: number, text: string, validation: ValidationResult}> {
  // Simple regex to find footnotes (e.g., "1. Text")
  // In a real PDF parser, this would be more robust
  const footnotePattern = /^(\d+)\.\s+(.+)$/gm;
  const results = [];
  let match;

  while ((match = footnotePattern.exec(text)) !== null) {
    const id = parseInt(match[1]);
    const content = match[2];
    results.push({
      id,
      text: content,
      validation: validateCitation(content)
    });
  }

  return results;
}
