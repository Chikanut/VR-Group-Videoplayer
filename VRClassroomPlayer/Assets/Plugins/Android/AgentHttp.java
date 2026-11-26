package com.vrclass.player;

import java.io.BufferedInputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;

/**
 * Minimal HTTP/1.1 GET over a plain socket, for the instructor server only (uvicorn: always
 * Content-Length, never chunked for our routes). Java's HttpURLConnection is blocked from
 * plain HTTP by the network security config Unity generates (cleartextTrafficPermitted=false,
 * and Player Settings > "Allow downloads over HTTP" does not change it in Unity 6000.6).
 */
final class AgentHttp {
    final int status;
    final long contentLength; // -1 = unknown
    final InputStream body;
    private final Socket socket;

    private AgentHttp(Socket socket, int status, long contentLength, InputStream body) {
        this.socket = socket;
        this.status = status;
        this.contentLength = contentLength;
        this.body = body;
    }

    /** rangeFrom > 0 asks for "bytes=rangeFrom-". The caller must close(). */
    static AgentHttp get(String url, long rangeFrom, int connectTimeoutMs, int readTimeoutMs) throws IOException {
        URI uri = URI.create(url);
        if (!"http".equals(uri.getScheme())) throw new IOException("Only http:// is supported: " + url);
        String host = uri.getHost();
        int port = uri.getPort() > 0 ? uri.getPort() : 80;
        String path = uri.getRawPath() == null || uri.getRawPath().isEmpty() ? "/" : uri.getRawPath();
        if (uri.getRawQuery() != null) path += "?" + uri.getRawQuery();

        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress(host, port), connectTimeoutMs);
            socket.setSoTimeout(readTimeoutMs);
            String request = "GET " + path + " HTTP/1.1\r\nHost: " + host + ":" + port
                    + (rangeFrom > 0 ? "\r\nRange: bytes=" + rangeFrom + "-" : "")
                    + "\r\nConnection: close\r\n\r\n";
            OutputStream out = socket.getOutputStream();
            out.write(request.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            InputStream in = new BufferedInputStream(socket.getInputStream(), 1 << 16);
            String statusLine = readLine(in);
            String[] parts = statusLine.split(" ");
            if (parts.length < 2 || !parts[0].startsWith("HTTP/")) throw new IOException("Bad response: " + statusLine);
            int status = Integer.parseInt(parts[1]);
            long length = -1;
            for (String line = readLine(in); !line.isEmpty(); line = readLine(in)) {
                int colon = line.indexOf(':');
                if (colon <= 0) continue;
                String name = line.substring(0, colon).trim();
                String value = line.substring(colon + 1).trim();
                if (name.equalsIgnoreCase("Content-Length")) length = Long.parseLong(value);
                if (name.equalsIgnoreCase("Transfer-Encoding") && !value.equalsIgnoreCase("identity")) {
                    throw new IOException("Unsupported Transfer-Encoding: " + value);
                }
            }
            return new AgentHttp(socket, status, length, length >= 0 ? new Limited(in, length) : in);
        } catch (IOException | RuntimeException e) {
            try { socket.close(); } catch (IOException ignored) { }
            throw e instanceof IOException ? (IOException) e : new IOException(e.getMessage(), e);
        }
    }

    /** Small text body (JSON answers). */
    String readText(int maxBytes) throws IOException {
        byte[] buffer = new byte[4096];
        java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
        for (int n; (n = body.read(buffer)) > 0 && bytes.size() < maxBytes; ) bytes.write(buffer, 0, n);
        return new String(bytes.toByteArray(), StandardCharsets.UTF_8);
    }

    void close() {
        try { socket.close(); } catch (IOException ignored) { }
    }

    private static String readLine(InputStream in) throws IOException {
        StringBuilder line = new StringBuilder();
        while (true) {
            int b = in.read();
            if (b < 0) throw new EOFException("Connection closed in headers");
            if (b == '\n') return line.toString();
            if (b != '\r') line.append((char) b);
            if (line.length() > 8192) throw new IOException("Header line too long");
        }
    }

    /** Stops at Content-Length; a connection that ends early is an error, not a short file. */
    private static final class Limited extends FilterInputStream {
        private long left;

        Limited(InputStream in, long length) {
            super(in);
            left = length;
        }

        @Override
        public int read() throws IOException {
            byte[] one = new byte[1];
            return read(one, 0, 1) < 0 ? -1 : one[0] & 0xFF;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (left <= 0) return -1;
            int n = super.read(b, off, (int) Math.min(len, left));
            if (n < 0) throw new EOFException("Connection closed with " + left + " bytes left");
            left -= n;
            return n;
        }
    }
}
