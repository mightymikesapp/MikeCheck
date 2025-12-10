import { useState, useEffect, useRef } from 'react';
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle, CheckCircle2, XCircle, Wand2 } from "lucide-react";
import { validateCitation, ValidationResult } from "@/lib/bluebook";
import { cn } from "@/lib/utils";

export default function CitationEditor() {
  const [text, setText] = useState("");
  const [validations, setValidations] = useState<Array<{line: number, result: ValidationResult}>>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const lines = text.split('\n');
    const newValidations = lines.map((line, index) => {
      if (!line.trim()) return null;
      // Only validate if it looks like a citation (basic heuristic)
      if (line.match(/\d/) || line.includes('v.') || line.includes('In re')) {
        return {
          line: index,
          result: validateCitation(line)
        };
      }
      return null;
    }).filter(Boolean) as Array<{line: number, result: ValidationResult}>;

    setValidations(newValidations);
  }, [text]);

  const applyCorrection = (lineIndex: number, correctedText: string) => {
    const lines = text.split('\n');
    lines[lineIndex] = correctedText;
    setText(lines.join('\n'));
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-[600px]">
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-muted-foreground">Citation Draft</h3>
        <Textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type your citations here (one per line)...&#10;Example: Roe v. Wade, 410 U.S. 113 (1973)"
          className="flex-1 font-mono text-sm resize-none p-4 leading-relaxed"
          spellCheck={false}
        />
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-muted-foreground">Live Validation</h3>
        <div className="flex-1 overflow-y-auto space-y-3 pr-2">
          {validations.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground border-2 border-dashed border-border rounded-lg">
              <CheckCircle2 className="w-8 h-8 mb-2 opacity-20" />
              <p>Start typing to see validation results</p>
            </div>
          )}
          
          {validations.map((val) => (
            <Card key={val.line} className={cn(
              "border-l-4 transition-all duration-300",
              val.result.isValid ? "border-l-green-500" : "border-l-destructive"
            )}>
              <CardHeader className="py-3 px-4 bg-accent/10">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-mono text-muted-foreground">
                    Line {val.line + 1} • {val.result.type.toUpperCase()}
                  </CardTitle>
                  {val.result.isValid ? (
                    <div className="flex items-center text-green-600 text-xs font-medium">
                      <CheckCircle2 className="w-3 h-3 mr-1" /> Valid
                    </div>
                  ) : (
                    <div className="flex items-center text-destructive text-xs font-medium">
                      <XCircle className="w-3 h-3 mr-1" /> Issues Found
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent className="py-3 px-4">
                <p className="font-mono text-sm mb-2 bg-background p-2 rounded border border-border">
                  {text.split('\n')[val.line]}
                </p>
                
                {!val.result.isValid && (
                  <div className="space-y-2 mt-3">
                    {val.result.issues.map((issue, idx) => (
                      <div key={idx} className="flex items-start gap-2 text-xs text-destructive bg-destructive/5 p-2 rounded">
                        <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                        <span>{issue}</span>
                      </div>
                    ))}
                    
                    {val.result.corrected && (
                      <Button 
                        size="sm" 
                        variant="outline" 
                        className="w-full mt-2 text-xs h-8 border-green-200 hover:bg-green-50 hover:text-green-700 text-green-600"
                        onClick={() => applyCorrection(val.line, val.result.corrected!)}
                      >
                        <Wand2 className="w-3 h-3 mr-2" />
                        Fix It: {val.result.corrected}
                      </Button>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
