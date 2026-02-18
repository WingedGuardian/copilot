/**
 * WhatsApp client wrapper using Baileys.
 * Based on OpenClaw's working implementation.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  downloadMediaMessage,
} from '@whiskeysockets/baileys';

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { Boom } from '@hapi/boom';
import qrcode from 'qrcode-terminal';
import pino from 'pino';

const MAX_MEDIA_BYTES = 25 * 1024 * 1024; // 25 MB

/** Persistent media directory matching Telegram/Discord channels. */
const MEDIA_DIR = path.join(os.homedir(), '.nanobot', 'media');

const VERSION = '0.1.0';

export interface RejectedFile {
  filename: string;
  size: number;
  reason: string;
}

export interface InboundMessage {
  id: string;
  sender: string;
  pn: string;
  content: string;
  timestamp: number;
  isGroup: boolean;
  audioPath?: string;
  documentPath?: string;
  imagePath?: string;
  rejectedFiles?: RejectedFile[];
}

export interface WhatsAppClientOptions {
  authDir: string;
  onMessage: (msg: InboundMessage) => void;
  onQR: (qr: string) => void;
  onStatus: (status: string) => void;
}

export class WhatsAppClient {
  private sock: any = null;
  private options: WhatsAppClientOptions;
  private reconnecting = false;

  constructor(options: WhatsAppClientOptions) {
    this.options = options;
  }

  async connect(): Promise<void> {
    const logger = pino({ level: 'silent' });
    const { state, saveCreds } = await useMultiFileAuthState(this.options.authDir);
    const { version } = await fetchLatestBaileysVersion();

    console.log(`Using Baileys version: ${version.join('.')}`);

    // Create socket following OpenClaw's pattern
    this.sock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      version,
      logger,
      printQRInTerminal: false,
      browser: ['nanobot', 'cli', VERSION],
      syncFullHistory: false,
      markOnlineOnConnect: false,
    });

    // Handle WebSocket errors
    if (this.sock.ws && typeof this.sock.ws.on === 'function') {
      this.sock.ws.on('error', (err: Error) => {
        console.error('WebSocket error:', err.message);
      });
    }

    // Handle connection updates
    this.sock.ev.on('connection.update', async (update: any) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        // Display QR code in terminal
        console.log('\n📱 Scan this QR code with WhatsApp (Linked Devices):\n');
        qrcode.generate(qr, { small: true });
        this.options.onQR(qr);
      }

      if (connection === 'close') {
        const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        console.log(`Connection closed. Status: ${statusCode}, Will reconnect: ${shouldReconnect}`);
        this.options.onStatus('disconnected');

        if (shouldReconnect && !this.reconnecting) {
          this.reconnecting = true;
          console.log('Reconnecting in 5 seconds...');
          setTimeout(() => {
            this.reconnecting = false;
            this.connect();
          }, 5000);
        }
      } else if (connection === 'open') {
        console.log('✅ Connected to WhatsApp');
        this.options.onStatus('connected');
      }
    });

    // Save credentials on update
    this.sock.ev.on('creds.update', saveCreds);

    // Ensure persistent media directory exists
    fs.mkdirSync(MEDIA_DIR, { recursive: true });

    // Handle incoming messages
    this.sock.ev.on('messages.upsert', async ({ messages, type }: { messages: any[]; type: string }) => {
      if (type !== 'notify') return;

      for (const msg of messages) {
        // Skip own messages
        if (msg.key.fromMe) continue;

        // Skip status updates
        if (msg.key.remoteJid === 'status@broadcast') continue;

        const content = this.extractMessageContent(msg);
        if (!content) continue;

        const isGroup = msg.key.remoteJid?.endsWith('@g.us') || false;
        const rejectedFiles: RejectedFile[] = [];

        // Download voice note audio if present
        let audioPath: string | undefined;
        if (msg.message?.audioMessage) {
          try {
            const buffer = await downloadMediaMessage(msg, 'buffer', {});
            if ((buffer as Buffer).length > MAX_MEDIA_BYTES) {
              rejectedFiles.push({ filename: 'voice_note.ogg', size: (buffer as Buffer).length, reason: 'exceeds 25MB limit' });
            } else {
              const filename = `nanobot_audio_${msg.key.id || Date.now()}.ogg`;
              audioPath = path.join(MEDIA_DIR, filename);
              fs.writeFileSync(audioPath, buffer as Buffer);
              console.log(`Voice note saved to ${audioPath}`);
            }
          } catch (err) {
            console.error('Failed to download voice note:', err);
          }
        }

        // Download document if present
        let documentPath: string | undefined;
        if (msg.message?.documentMessage) {
          const origName = msg.message.documentMessage.fileName || `doc_${msg.key.id || Date.now()}`;
          try {
            const buffer = await downloadMediaMessage(msg, 'buffer', {});
            if ((buffer as Buffer).length > MAX_MEDIA_BYTES) {
              rejectedFiles.push({ filename: origName, size: (buffer as Buffer).length, reason: 'exceeds 25MB limit' });
            } else {
              const filename = `nanobot_${msg.key.id || Date.now()}_${origName}`;
              documentPath = path.join(MEDIA_DIR, filename);
              fs.writeFileSync(documentPath, buffer as Buffer);
              console.log(`Document saved to ${documentPath}`);
            }
          } catch (err) {
            console.error('Failed to download document:', err);
          }
        }

        // Download image if present
        let imagePath: string | undefined;
        if (msg.message?.imageMessage) {
          try {
            const buffer = await downloadMediaMessage(msg, 'buffer', {});
            if ((buffer as Buffer).length > MAX_MEDIA_BYTES) {
              rejectedFiles.push({ filename: `image_${msg.key.id}.jpg`, size: (buffer as Buffer).length, reason: 'exceeds 25MB limit' });
            } else {
              const filename = `nanobot_image_${msg.key.id || Date.now()}.jpg`;
              imagePath = path.join(MEDIA_DIR, filename);
              fs.writeFileSync(imagePath, buffer as Buffer);
              console.log(`Image saved to ${imagePath}`);
            }
          } catch (err) {
            console.error('Failed to download image:', err);
          }
        }

        this.options.onMessage({
          id: msg.key.id || '',
          sender: msg.key.remoteJid || '',
          pn: msg.key.remoteJidAlt || '',
          content,
          timestamp: msg.messageTimestamp as number,
          isGroup,
          audioPath,
          documentPath,
          imagePath,
          ...(rejectedFiles.length > 0 ? { rejectedFiles } : {}),
        });
      }
    });
  }

  private extractMessageContent(msg: any): string | null {
    const message = msg.message;
    if (!message) return null;

    // Text message
    if (message.conversation) {
      return message.conversation;
    }

    // Extended text (reply, link preview)
    if (message.extendedTextMessage?.text) {
      return message.extendedTextMessage.text;
    }

    // Image with caption
    if (message.imageMessage?.caption) {
      return `[Image] ${message.imageMessage.caption}`;
    }

    // Video with caption
    if (message.videoMessage?.caption) {
      return `[Video] ${message.videoMessage.caption}`;
    }

    // Document with caption
    if (message.documentMessage?.caption) {
      return `[Document] ${message.documentMessage.caption}`;
    }

    // Voice/Audio message
    if (message.audioMessage) {
      return `[Voice Message]`;
    }

    // Captionless media fallbacks (ensures message reaches Python even without text)
    if (message.documentMessage) {
      return `[Document: ${message.documentMessage.fileName || 'document'}]`;
    }
    if (message.imageMessage) {
      return `[Image]`;
    }
    if (message.videoMessage) {
      return `[Video]`;
    }

    return null;
  }

  private isUsableJid(jid: string): boolean {
    // Baileys' jidDecode crashes on @lid JIDs — only allow @s.whatsapp.net and @g.us
    return jid.endsWith('@s.whatsapp.net') || jid.endsWith('@g.us');
  }

  async sendMessage(to: string, text: string): Promise<void> {
    if (!this.sock) throw new Error('Not connected');
    if (!this.isUsableJid(to)) {
      console.warn(`Skipping sendMessage: unsupported JID format "${to}"`);
      return;
    }
    await this.sock.sendMessage(to, { text });
  }

  async markRead(jid: string, messageIds: string[]): Promise<void> {
    if (!this.sock) return;
    if (!this.isUsableJid(jid)) return;
    await this.sock.readMessages([{ remoteJid: jid, id: messageIds[0], participant: undefined }]);
  }

  async sendPresence(jid: string, type: 'composing' | 'paused'): Promise<void> {
    if (!this.sock) return;
    if (!this.isUsableJid(jid)) return;
    await this.sock.presenceSubscribe(jid);
    await this.sock.sendPresenceUpdate(type, jid);
  }

  async disconnect(): Promise<void> {
    if (this.sock) {
      this.sock.end(undefined);
      this.sock = null;
    }
  }
}
