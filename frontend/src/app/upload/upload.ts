import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-upload',
  imports: [FormsModule],
  templateUrl: './upload.html',
  styleUrl: './upload.css',
})
export class Upload {
  url = '';
  submitting = false;
  message = '';
  error = false;

  async onSubmit(): Promise<void> {
    if (!this.url) return;

    this.submitting = true;
    this.message = '';
    this.error = false;

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: this.url }),
      });

      if (!res.ok) throw new Error(`Server responded with ${res.status}`);

      this.message = 'Upload started successfully!';
      this.url = '';
    } catch {
      this.message = 'Upload failed. Is the backend running?';
      this.error = true;
    } finally {
      this.submitting = false;
    }
  }
}
