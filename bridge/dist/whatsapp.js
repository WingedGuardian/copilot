/**
 * WhatsApp client wrapper using Baileys.
 * Based on OpenClaw's working implementation.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import makeWASocket, { DisconnectReason, useMultiFileAuthState, fetchLatestBaileysVersion, makeCacheableSignalKeyStore, downloadMediaMessage, } from '@whiskeysockets/baileys';
import * as fs from 'fs';
import * as path from 'path';
import qrcode from 'qrcode-terminal';
import pino from 'pino';
const MAX_MEDIA_BYTES = 25 * 1024 * 1024; // 25 MB
const VERSION = '0.1.0';
export class WhatsAppClient {
    sock = null;
    options;
    reconnecting = false;
    constructor(options) {
        this.options = options;
    }
    async connect() {
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
            this.sock.ws.on('error', (err) => {
                console.error('WebSocket error:', err.message);
            });
        }
        // Handle connection updates
        this.sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                // Display QR code in terminal
                console.log('\n📱 Scan this QR code with WhatsApp (Linked Devices):\n');
                qrcode.generate(qr, { small: true });
                this.options.onQR(qr);
            }
            if (connection === 'close') {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
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
            }
            else if (connection === 'open') {
                console.log('✅ Connected to WhatsApp');
                this.options.onStatus('connected');
            }
        });
        // Save credentials on update
        this.sock.ev.on('creds.update', saveCreds);
        // Handle incoming messages
        this.sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify')
                return;
            for (const msg of messages) {
                // Skip own messages
                if (msg.key.fromMe)
                    continue;
                // Skip status updates
                if (msg.key.remoteJid === 'status@broadcast')
                    continue;
                const content = this.extractMessageContent(msg);
                if (!content)
                    continue;
                const isGroup = msg.key.remoteJid?.endsWith('@g.us') || false;
                // Download voice note audio if present
                let audioPath;
                if (msg.message?.audioMessage) {
                    try {
                        const buffer = await downloadMediaMessage(msg, 'buffer', {});
                        if (buffer.length > MAX_MEDIA_BYTES) {
                            console.warn(`Audio too large (${buffer.length} bytes), skipping`);
                        }
                        else {
                            const tmpDir = '/tmp';
                            const filename = `nanobot_audio_${msg.key.id || Date.now()}.ogg`;
                            audioPath = path.join(tmpDir, filename);
                            fs.writeFileSync(audioPath, buffer);
                            console.log(`Voice note saved to ${audioPath}`);
                        }
                    }
                    catch (err) {
                        console.error('Failed to download voice note:', err);
                    }
                }
                // Download document if present
                let documentPath;
                if (msg.message?.documentMessage) {
                    try {
                        const buffer = await downloadMediaMessage(msg, 'buffer', {});
                        if (buffer.length > MAX_MEDIA_BYTES) {
                            console.warn(`Document too large (${buffer.length} bytes), skipping`);
                        }
                        else {
                            const tmpDir = '/tmp';
                            const origName = msg.message.documentMessage.fileName || `doc_${msg.key.id || Date.now()}`;
                            const filename = `nanobot_${origName}`;
                            documentPath = path.join(tmpDir, filename);
                            fs.writeFileSync(documentPath, buffer);
                            console.log(`Document saved to ${documentPath}`);
                        }
                    }
                    catch (err) {
                        console.error('Failed to download document:', err);
                    }
                }
                // Download image if present
                let imagePath;
                if (msg.message?.imageMessage) {
                    try {
                        const buffer = await downloadMediaMessage(msg, 'buffer', {});
                        if (buffer.length > MAX_MEDIA_BYTES) {
                            console.warn(`Image too large (${buffer.length} bytes), skipping`);
                        }
                        else {
                            const tmpDir = '/tmp';
                            const filename = `nanobot_image_${msg.key.id || Date.now()}.jpg`;
                            imagePath = path.join(tmpDir, filename);
                            fs.writeFileSync(imagePath, buffer);
                            console.log(`Image saved to ${imagePath}`);
                        }
                    }
                    catch (err) {
                        console.error('Failed to download image:', err);
                    }
                }
                this.options.onMessage({
                    id: msg.key.id || '',
                    sender: msg.key.remoteJid || '',
                    pn: msg.key.remoteJidAlt || '',
                    content,
                    timestamp: msg.messageTimestamp,
                    isGroup,
                    audioPath,
                    documentPath,
                    imagePath,
                });
            }
        });
    }
    extractMessageContent(msg) {
        const message = msg.message;
        if (!message)
            return null;
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
        return null;
    }
    isUsableJid(jid) {
        // Baileys' jidDecode crashes on @lid JIDs — only allow @s.whatsapp.net and @g.us
        return jid.endsWith('@s.whatsapp.net') || jid.endsWith('@g.us');
    }
    async sendMessage(to, text) {
        if (!this.sock)
            throw new Error('Not connected');
        if (!this.isUsableJid(to)) {
            console.warn(`Skipping sendMessage: unsupported JID format "${to}"`);
            return;
        }
        await this.sock.sendMessage(to, { text });
    }
    async markRead(jid, messageIds) {
        if (!this.sock)
            return;
        if (!this.isUsableJid(jid))
            return;
        await this.sock.readMessages([{ remoteJid: jid, id: messageIds[0], participant: undefined }]);
    }
    async sendPresence(jid, type) {
        if (!this.sock)
            return;
        if (!this.isUsableJid(jid))
            return;
        await this.sock.presenceSubscribe(jid);
        await this.sock.sendPresenceUpdate(type, jid);
    }
    async disconnect() {
        if (this.sock) {
            this.sock.end(undefined);
            this.sock = null;
        }
    }
}
