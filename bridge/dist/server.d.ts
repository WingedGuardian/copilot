/**
 * WebSocket server for Python-Node.js bridge communication.
 */
export declare class BridgeServer {
    private port;
    private authDir;
    private wss;
    private wa;
    private clients;
    constructor(port: number, authDir: string);
    start(): Promise<void>;
    private handleCommand;
    private broadcast;
    stop(): Promise<void>;
}
