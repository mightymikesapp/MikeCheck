import axios from 'axios';

// Create an axios instance with default config
export const api = axios.create({
  baseURL: '/api', // We will proxy this in vite.config.ts
  headers: {
    'Content-Type': 'application/json',
  },
});

// Define types for API responses based on backend analysis
export interface TreatmentResult {
  citation: string;
  case_name?: string;
  valid: boolean;
  confidence: number;
  overall_treatment: string;
  citing_cases_count: number;
  treatment_summary: {
    negative_signals: number;
    positive_signals: number;
    neutral_citations: number;
  };
  warnings: string[];
  recommendation: string;
}

export interface SearchResult {
  results: Array<{
    citation: string;
    case_name: string;
    similarity: number;
    snippet: string;
  }>;
}

export interface ResearchResult {
  report: string;
  citations_analyzed: number;
}

// API methods
export const mikeCheckApi = {
  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/analyze/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  analyzeCitation: async (citation: string) => {
    const response = await api.post<TreatmentResult>('/herding/analyze', { citation });
    return response.data;
  },

  searchSimilar: async (query: string, limit: number = 10) => {
    const response = await api.post<SearchResult>('/search/similar', { query, limit });
    return response.data;
  },

  runResearch: async (citations: string[], keyQuestions?: string[]) => {
    const response = await api.post<ResearchResult>('/research/analyze', { 
      citations, 
      key_questions: keyQuestions 
    });
    return response.data;
  }
};
