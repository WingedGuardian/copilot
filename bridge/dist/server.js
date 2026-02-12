/**
 * WebSocket server for Python-Node.js bridge communication.
 */
import { WebSocketServer, WebSocket } from 'ws';
import { WhatsAppClient } from './whatsapp.js';
export class BridgeServer {
    port;
    authDir;
    wss = null;
    wa = null;
    clients = new Set();
    constructor(port, authDir) {
        this.port = port;
        this.authDir = authDir;
    }
    async start() {
        // Create WebSocket server
        this.wss = new WebSocketServer({ port: this.port });
        console.log(`🌉 Bridge server listening on ws://localhost:${this.port}`);
        // Initialize WhatsApp client
        this.wa = new WhatsAppClient({
            authDir: this.authDir,
            onMessage: (msg) => this.broadcast({ type: 'message', ...msg }),
            onQR: (qr) => this.broadcast({ type: 'qr', qr }),
            onStatus: (status) => this.broadcast({ type: 'status', status }),
        });
        // Handle WebSocket connections
        this.wss.on('connection', (ws) => {
            console.log('🔗 Python client connected');
            this.clients.add(ws);
            ws.on('message', async (data) => {
                try {
                    const cmd = JSON.parse(data.toString());
                    await this.handleCommand(cmd);
                    ws.send(JSON.stringify({ type: 'sent', to: cmd.to }));
                }
                catch (error) {
                    console.error('Error handling command:', error);
                    ws.send(JSON.stringify({ type: 'error', error: String(error) }));
                }
            });
            ws.on('close', () => {
                console.log('🔌 Python client disconnected');
                this.clients.delete(ws);
            });
            ws.on('error', (error) => {
                console.error('WebSocket error:', error);
                this.clients.delete(ws);
            });
        });
        // Connect to WhatsApp
        await this.wa.connect();
    }
    async handleCommand(cmd) {
        if (cmd.type === 'send' && this.wa) {
            await this.wa.sendMessage(cmd.to, cmd.text);
        }
    }
    broadcast(msg) {
        const data = JSON.stringify(msg);
        for (const client of this.clients) {
            if (client.readyState === WebSocket.OPEN) {
                client.send(data);
            }
        }
    }
    async stop() {
        // Close all client connections
        for (const client of this.clients) {
            client.close();
        }
        this.clients.clear();
        // Close WebSocket server
        if (this.wss) {
            this.wss.close();
            this.wss = null;
        }
        // Disconnect WhatsApp
        if (this.wa) {
            await this.wa.disconnect();
            this.wa = null;
        }
    }
}
