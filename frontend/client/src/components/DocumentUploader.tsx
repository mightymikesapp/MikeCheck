import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

interface DocumentUploaderProps {
  onUploadComplete?: (file: File) => void;
  className?: string;
}

export default function DocumentUploader({ onUploadComplete, className }: DocumentUploaderProps) {
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState("");

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setFileName(file.name);
    setUploadStatus("uploading");
    setProgress(0);

    // Simulate upload progress
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setUploadStatus("success");
          if (onUploadComplete) onUploadComplete(file);
          return 100;
        }
        return prev + 10;
      });
    }, 200);
  }, [onUploadComplete]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt']
    },
    maxFiles: 1
  });

  return (
    <div className={cn("w-full", className)}>
      <div
        {...getRootProps()}
        className={cn(
          "relative border-2 border-dashed transition-all duration-300 ease-out cursor-pointer group overflow-hidden",
          "h-64 flex flex-col items-center justify-center text-center p-8",
          isDragActive 
            ? "border-primary bg-primary/5" 
            : "border-border hover:border-primary/50 hover:bg-accent/50",
          uploadStatus === "success" && "border-green-500 bg-green-50/10",
          uploadStatus === "error" && "border-destructive bg-destructive/5"
        )}
      >
        <input {...getInputProps()} />
        
        {uploadStatus === "idle" && (
          <>
            <div className="w-16 h-16 mb-6 rounded-full bg-accent flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
              <Upload className="w-8 h-8 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <h3 className="text-lg font-bold text-foreground mb-2">
              {isDragActive ? "Drop document here" : "Upload Legal Document"}
            </h3>
            <p className="text-sm text-muted-foreground max-w-xs mx-auto">
              Drag and drop your PDF or TXT file here, or click to browse.
              <br />
              <span className="text-xs opacity-70 mt-2 block">Max file size: 50MB</span>
            </p>
          </>
        )}

        {uploadStatus === "uploading" && (
          <div className="w-full max-w-md space-y-4">
            <div className="w-16 h-16 mx-auto rounded-full bg-primary/10 flex items-center justify-center animate-pulse">
              <FileText className="w-8 h-8 text-primary" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">{fileName}</p>
              <p className="text-xs text-muted-foreground">Analyzing citations...</p>
            </div>
            <Progress value={progress} className="h-1" />
          </div>
        )}

        {uploadStatus === "success" && (
          <div className="w-full max-w-md space-y-4 animate-in fade-in zoom-in duration-300">
            <div className="w-16 h-16 mx-auto rounded-full bg-green-100 flex items-center justify-center">
              <CheckCircle2 className="w-8 h-8 text-green-600" />
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-foreground">Analysis Complete</h3>
              <p className="text-sm text-muted-foreground">{fileName} ready for review</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
