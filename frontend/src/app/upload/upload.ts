import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface StoredPanelResult {
  panel_index: number;
  storage_key: string;
  byte_size: number;
  content_type: string;
  public_url: string;
}

interface UploadWebscrapeResponse {
  chapter_id: string;
  quality: string;
  page_count: number;
  fetched_ok: number;
  stored_panels: number;
  errors: { index: number; url: string; detail: string }[];
  pages: {
    index: number;
    panel_count: number;
    stored_panels: StoredPanelResult[];
  }[];
}

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
      const res = await fetch('/api/upload-webscrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: this.url }),
      });

      const data = (await res.json()) as UploadWebscrapeResponse & { detail?: string };

      if (!res.ok) {
        throw new Error(data.detail ?? `Server responded with ${res.status}`);
      }

      this.message = `Stored ${data.stored_panels} panel(s) from ${data.fetched_ok}/${data.page_count} page(s).`;
      this.url = '';
    } catch (err) {
      this.message =
        err instanceof Error ? err.message : 'Upload failed. Is the backend running?';
      this.error = true;
    } finally {
      this.submitting = false;
    }
  }
}
