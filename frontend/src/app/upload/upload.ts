import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface JobView {
  job_id: string;
  state: 'RUNNING' | 'DONE' | 'ERROR';
  log: string[];
  summary: { chapter_id?: string; quality?: string; pages?: number; panels?: number };
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
    this.message = 'Starting ingest…';
    this.error = false;

    try {
      // Kick off an async ingest job on the ingestion service (proxied /ingest).
      const res = await fetch('/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: this.url, quality: 'data-saver' }),
      });
      const started = (await res.json()) as JobView & { detail?: string };
      if (!res.ok) {
        throw new Error(started.detail ?? `Server responded with ${res.status}`);
      }

      // Poll the job until it finishes.
      const job = await this.pollJob(started.job_id);
      if (job.state === 'ERROR') {
        throw new Error(job.log[job.log.length - 1] ?? 'Ingest failed');
      }
      const s = job.summary;
      this.message = `Ingested ${s.panels ?? 0} panel(s) from ${s.pages ?? 0} page(s).`;
      this.url = '';
    } catch (err) {
      this.message =
        err instanceof Error ? err.message : 'Ingest failed. Is the ingestion service running?';
      this.error = true;
    } finally {
      this.submitting = false;
    }
  }

  private async pollJob(jobId: string): Promise<JobView> {
    // Poll every 2s; ingest of a chapter can take a while (CPU inference).
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      const res = await fetch(`/ingest/${jobId}`);
      const job = (await res.json()) as JobView;
      const done = job.summary?.panels;
      this.message = job.state === 'RUNNING'
        ? `Ingesting… ${job.log[job.log.length - 1] ?? ''}`
        : this.message;
      if (job.state !== 'RUNNING') {
        return job;
      }
      void done;
    }
  }
}
