package com.vrclass.player;

import android.util.Base64;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;

/**
 * Minimal WebSocket client (RFC 6455, text messages only) for the agent's link to the
 * instructor server. A plain socket: no library, and not subject to the app's
 * cleartext-HTTP policy. Pings from the server are answered here; a silent socket
 * (no frame within readTimeoutMs, while the server pings every 20s) counts as dead.
 */
final class AgentWs {
    private static final String GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    private static final SecureRandom RANDOM = new SecureRandom();

    private final Socket socket;
    private final InputStream in;
    private final OutputStream out;

    private AgentWs(Socket socket) throws IOException {
        this.socket = socket;
        this.in = new BufferedInputStream(socket.getInputStream());
        this.out = socket.getOutputStream();
    }

    static AgentWs connect(String host, int port, String path, int connectTimeoutMs, int readTimeoutMs) throws IOException {
        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress(host, port), connectTimeoutMs);
            socket.setTcpNoDelay(true);
            socket.setKeepAlive(true);
            socket.setSoTimeout(connectTimeoutMs);
            AgentWs ws = new AgentWs(socket);
            ws.handshake(host, port, path);
            socket.setSoTimeout(readTimeoutMs);
            return ws;
        } catch (IOException | RuntimeException e) {
            try { socket.close(); } catch (IOException ignored) { }
            throw e;
        }
    }

    private void handshake(String host, int port, String path) throws IOException {
        byte[] nonce = new byte[16];
        RANDOM.nextBytes(nonce);
        String key = Base64.encodeToString(nonce, Base64.NO_WRAP);
        String request = "GET " + path + " HTTP/1.1\r\nHost: " + host + ":" + port
                + "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + key
                + "\r\nSec-WebSocket-Version: 13\r\n\r\n";
        out.write(request.getBytes(StandardCharsets.US_ASCII));
        out.flush();

        String status = readLine();
        if (!status.contains(" 101")) throw new IOException("Handshake refused: " + status);
        String accept = null;
        for (String line = readLine(); !line.isEmpty(); line = readLine()) {
            int colon = line.indexOf(':');
            if (colon > 0 && line.substring(0, colon).trim().equalsIgnoreCase("Sec-WebSocket-Accept")) {
                accept = line.substring(colon + 1).trim();
            }
        }
        if (!expectedAccept(key).equals(accept)) throw new IOException("Bad Sec-WebSocket-Accept");
    }

    static String expectedAccept(String key) {
        try {
            byte[] sha1 = MessageDigest.getInstance("SHA-1").digest((key + GUID).getBytes(StandardCharsets.US_ASCII));
            return Base64.encodeToString(sha1, Base64.NO_WRAP);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private String readLine() throws IOException {
        StringBuilder line = new StringBuilder();
        while (true) {
            int b = in.read();
            if (b < 0) throw new EOFException("Connection closed during handshake");
            if (b == '\n') break;
            if (b != '\r') line.append((char) b);
            if (line.length() > 8192) throw new IOException("Header line too long");
        }
        return line.toString();
    }

    /** Thread-safe. Client frames must be masked. */
    synchronized void sendText(String text) throws IOException {
        sendFrame(0x1, text.getBytes(StandardCharsets.UTF_8));
    }

    private synchronized void sendFrame(int opcode, byte[] payload) throws IOException {
        ByteArrayOutputStream frame = new ByteArrayOutputStream(payload.length + 14);
        frame.write(0x80 | opcode);
        int len = payload.length;
        if (len < 126) {
            frame.write(0x80 | len);
        } else if (len <= 0xFFFF) {
            frame.write(0x80 | 126);
            frame.write(len >>> 8);
            frame.write(len);
        } else {
            frame.write(0x80 | 127);
            for (int shift = 56; shift >= 0; shift -= 8) frame.write((int) (((long) len) >>> shift));
        }
        byte[] mask = new byte[4];
        RANDOM.nextBytes(mask);
        frame.write(mask, 0, 4);
        for (int i = 0; i < len; i++) frame.write(payload[i] ^ mask[i & 3]);
        out.write(frame.toByteArray());
        out.flush();
    }

    /** Blocks for the next text message; answers pings. Throws when the socket closes or goes silent. */
    String readText() throws IOException {
        ByteArrayOutputStream message = new ByteArrayOutputStream();
        while (true) {
            int b0 = readByte();
            int b1 = readByte();
            boolean fin = (b0 & 0x80) != 0;
            int opcode = b0 & 0x0F;
            long len = b1 & 0x7F;
            if (len == 126) {
                len = ((long) readByte() << 8) | readByte();
            } else if (len == 127) {
                len = 0;
                for (int i = 0; i < 8; i++) len = (len << 8) | readByte();
            }
            if (len > 16L * 1024 * 1024) throw new IOException("Frame too large: " + len);
            byte[] mask = null;
            if ((b1 & 0x80) != 0) {
                mask = new byte[4];
                readFully(mask);
            }
            byte[] payload = new byte[(int) len];
            readFully(payload);
            if (mask != null) for (int i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];

            switch (opcode) {
                case 0x9: sendFrame(0xA, payload); break;             // ping -> pong
                case 0xA: break;                                       // pong
                case 0x8: throw new EOFException("Server closed the WebSocket");
                case 0x0: case 0x1: case 0x2:
                    message.write(payload, 0, payload.length);
                    if (fin) return new String(message.toByteArray(), StandardCharsets.UTF_8);
                    break;
                default: throw new IOException("Unknown opcode " + opcode);
            }
        }
    }

    private int readByte() throws IOException {
        int b = in.read();
        if (b < 0) throw new EOFException("Connection closed");
        return b;
    }

    private void readFully(byte[] buffer) throws IOException {
        int off = 0;
        while (off < buffer.length) {
            int n = in.read(buffer, off, buffer.length - off);
            if (n < 0) throw new EOFException("Connection closed");
            off += n;
        }
    }

    /** Just drops the socket: a close frame could block behind a stuck send, and the server copes either way. */
    void close() {
        try { socket.close(); } catch (IOException ignored) { }
    }
}
