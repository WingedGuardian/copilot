/**
 * WhatsApp client wrapper using Baileys.
 * Based on OpenClaw's working implementation.
 */
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
}
export interface WhatsAppClientOptions {
    authDir: string;
    onMessage: (msg: InboundMessage) => void;
    onQR: (qr: string) => void;
    onStatus: (status: string) => void;
}
export declare class WhatsAppClient {
    private sock;
    private options;
    private reconnecting;
    constructor(options: WhatsAppClientOptions);
    connect(): Promise<void>;
    private extractMessageContent;
    sendMessage(to: string, text: string): Promise<void>;
    markRead(jid: string, messageIds: string[]): Promise<void>;
    sendPresence(jid: string, type: 'composing' | 'paused'): Promise<void>;
    disconnect(): Promise<void>;
}
