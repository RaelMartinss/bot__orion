/**
 * whatsapp_server/server.js
 * Servidor Node.js que expõe uma API REST para o Orion controlar o WhatsApp.
 *
 * Endpoints:
 *   GET  /status          → estado da conexão (qr | conectado | desconectado)
 *   GET  /qr              → QR code em ASCII para escanear
 *   POST /send            → { para: "5511999999999", mensagem: "texto" }
 *   GET  /contatos        → lista de contatos salvos
 *
 * Iniciar: node server.js
 * Porta: 3131 (configurável via PORT env)
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const fs = require('fs');
const path = require('path');

const PID_FILE = path.join(__dirname, 'sessao_wpp', 'chrome.pid');
const sessaoDir = path.join(__dirname, 'sessao_wpp', 'session');

// Mata apenas o Chrome da sessão anterior usando o PID salvo — não afeta o Chrome do usuário
if (fs.existsSync(PID_FILE)) {
    try {
        const oldPid = fs.readFileSync(PID_FILE, 'utf8').trim();
        require('child_process').execSync(`taskkill /F /T /PID ${oldPid}`, { stdio: 'ignore' });
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 800);
        console.log(`🧹 Chrome anterior (PID ${oldPid}) encerrado.`);
    } catch (_) { /* processo já estava morto */ }
    fs.unlinkSync(PID_FILE);
}

// Remove apenas Singleton locks do Chromium (NÃO toca em LOCK do LevelDB)
['SingletonLock', 'SingletonSocket', 'SingletonCookie'].forEach(lock => {
    const lockPath = path.join(sessaoDir, lock);
    if (fs.existsSync(lockPath)) {
        try { fs.unlinkSync(lockPath); }
        catch (_) {}
    }
});

const PORT = process.env.PORT || 3131;
const app = express();
app.use(express.json());

// ── Estado global ─────────────────────────────────────────────────────────────

let estado = 'inicializando'; // inicializando | qr | conectado | desconectado
let qrAtual = null;
let clientePronto = false;
let contatosCache = []; // cache carregado no evento ready

// ── Cliente WhatsApp ──────────────────────────────────────────────────────────

const client = new Client({
    authStrategy: new LocalAuth({ dataPath: './sessao_wpp' }),
    puppeteer: {
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    },
});

client.on('qr', (qr) => {
    estado = 'qr';
    qrAtual = qr;
    console.log('\n📱 Escaneie o QR Code abaixo com o WhatsApp:\n');
    qrcode.generate(qr, { small: true });
    console.log('\nOu acesse GET /qr para obter o código.');
});

client.on('ready', async () => {
    estado = 'conectado';
    clientePronto = true;
    qrAtual = null;
    console.log('✅ WhatsApp conectado e pronto!');

    // Salva PID do Chrome para matar precisamente na próxima inicialização
    try {
        const chromePid = client.pupBrowser.process().pid;
        if (chromePid) {
            fs.mkdirSync(path.dirname(PID_FILE), { recursive: true });
            fs.writeFileSync(PID_FILE, String(chromePid));
        }
    } catch (_) {}

    // Carrega contatos em background após conexão
    try {
        const todos = await client.getContacts();
        console.log(`📒 Total bruto: ${todos.length} contatos.`);

        // Acessa propriedades diretamente (são getters não-enumeráveis, JSON.stringify retorna {})
        const deContatos = todos
            .filter(c => c.isUser && c.isMyContact && !c.isGroup)
            .map(c => ({
                nome: c.name || c.pushname || c.shortName || '',
                numero: c.number || (c.id ? c.id.user : '') || '',
            }))
            .filter(c => c.nome && c.numero && !c.numero.includes('-'));

        // getChats() é mais confiável — usa id._serialized que já tem o formato certo (c.us ou lid)
        const chats = await client.getChats();
        const deChats = chats
            .filter(chat => !chat.isGroup && chat.name && chat.id)
            .map(chat => ({
                nome: chat.name || '',
                // id._serialized já contém "@c.us" ou "@lid" — usar diretamente no envio
                numero: chat.id._serialized || '',
                // Fallback numérico puro para matching no Python
                numeroUser: chat.id.user || '',
            }))
            .filter(c => c.nome && c.numero && !c.nome.includes('@'));

        // Merge: prioriza deContatos, complementa com deChats
        const vistos = new Set(deContatos.map(c => c.numero));
        contatosCache = [...deContatos, ...deChats.filter(c => !vistos.has(c.numero))];
        console.log(`📒 ${contatosCache.length} contatos válidos (${deContatos.length} agenda + ${deChats.length} chats).`);
    } catch (e) {
        console.warn('⚠️ Não foi possível carregar contatos:', e.message);
    }
});

client.on('disconnected', async (reason) => {
    estado = 'desconectado';
    clientePronto = false;
    console.log('❌ WhatsApp desconectado:', reason);
    // Reconecta automaticamente após 5s
    setTimeout(async () => {
        console.log('🔄 Reconectando WhatsApp...');
        try {
            await client.initialize();
        } catch (e) {
            console.warn('⚠️ Falha ao reconectar:', e.message);
        }
    }, 5000);
});

client.initialize();

// ── Endpoints REST ────────────────────────────────────────────────────────────

app.get('/status', (req, res) => {
    res.json({ estado, pronto: clientePronto });
});

app.get('/health', async (req, res) => {
    if (!clientePronto || !client.pupPage) {
        return res.status(503).json({ ok: false, motivo: 'não conectado' });
    }
    try {
        await client.pupPage.evaluate(() => true);
        res.json({ ok: true });
    } catch (e) {
        res.status(503).json({ ok: false, motivo: e.message });
    }
});

app.get('/qr', (req, res) => {
    if (!qrAtual) {
        return res.json({ qr: null, mensagem: estado === 'conectado' ? 'Já conectado.' : 'QR ainda não gerado.' });
    }
    res.json({ qr: qrAtual });
});

app.post('/send', async (req, res) => {
    const { para, mensagem } = req.body;

    if (!clientePronto) {
        return res.status(503).json({ erro: `WhatsApp não conectado. Estado: ${estado}` });
    }
    if (!para || !mensagem) {
        return res.status(400).json({ erro: 'Campos obrigatórios: para, mensagem' });
    }

    try {
        const chatId = para.includes('@') ? para : `${para.replace(/\D/g, '')}@c.us`;

        // Verifica se a página Puppeteer ainda está viva antes de tentar enviar
        if (!client.pupPage || client.pupPage.isClosed()) {
            return res.status(503).json({ erro: 'Página do WhatsApp Web não está disponível. Aguarde reconexão.' });
        }

        const enviarComRetry = async (tentativas = 3) => {
            for (let i = 0; i < tentativas; i++) {
                try {
                    // getChatById obtém referência fresca — evita detached Frame
                    const chat = await client.getChatById(chatId);
                    await chat.sendMessage(mensagem);
                    return;
                } catch (err) {
                    const transitorio = err.message && (
                        err.message.includes('detached Frame') ||
                        err.message.includes('Execution context') ||
                        err.message.includes('Target closed') ||
                        err.message.includes('LID')
                    );
                    if (transitorio && i < tentativas - 1) {
                        console.warn(`⚠️ Tentativa ${i + 1} falhou (${err.message.split('\n')[0]}) — aguardando...`);
                        await new Promise(r => setTimeout(r, 3000));
                        continue;
                    }
                    throw err;
                }
            }
        };
        await enviarComRetry();
        console.log(`📤 Mensagem enviada para ${chatId}: ${mensagem}`);
        res.json({ ok: true, para: chatId });
    } catch (err) {
        console.error('Erro ao enviar:', err.message);
        res.status(500).json({ erro: err.message });
    }
});

app.get('/contatos', (req, res) => {
    if (!clientePronto) {
        return res.status(503).json({ erro: 'WhatsApp não conectado.' });
    }
    // Cache preenchido pelo evento 'ready' — não recarregar aqui (evita race condition)
    res.json({ contatos: contatosCache });
});

// ── Start ─────────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
    console.log(`🟢 Orion WhatsApp Server rodando em http://localhost:${PORT}`);
});
