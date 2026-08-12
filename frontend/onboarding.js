/* ═══════════════════════════════════════════════════════════════════════════
   SICAR Áncash — Bienvenida, recorrido guiado y exploración por temáticas
   ───────────────────────────────────────────────────────────────────────────
   Módulo independiente: NO modifica ninguna función existente de script.js.
   Solo consume las globales ya definidas allí (selecciones, aplicarFiltros,
   triggerCascada, llenarChecklist, actualizarFiltrosSecundarios,
   actualizarFiltrosSubcuenca) y añade comportamiento nuevo encima.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    const $ = id => document.getElementById(id);

    /* ══════════════════════════════════════════════════════════════════════
       1. BIENVENIDA
       ──────────────────────────────────────────────────────────────────────
       Se muestra en CADA carga de la página: al entrar, al refrescar y al
       volver a abrir el visor. Así ningún visitante nuevo se queda sin la
       invitación al recorrido.
       ══════════════════════════════════════════════════════════════════════ */
    const overlay = $('bienvenida-overlay');

    function cerrarBienvenida() {
        overlay.classList.remove('visible');
        setTimeout(() => { overlay.style.display = 'none'; }, 300);
    }

    overlay.style.display = 'flex';
    requestAnimationFrame(() => overlay.classList.add('visible'));

    // Cerrar con Esc o pulsando fuera del cuadro
    overlay.addEventListener('click', e => { if (e.target === overlay) cerrarBienvenida(); });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && overlay.classList.contains('visible')) cerrarBienvenida();
    });

    $('bv-si').addEventListener('click', () => { cerrarBienvenida(); setTimeout(iniciarTour, 380); });
    $('bv-no').addEventListener('click', cerrarBienvenida);

    /* ══════════════════════════════════════════════════════════════════════
       2. RECORRIDO GUIADO
       ══════════════════════════════════════════════════════════════════════ */
    const capaTour  = $('tour-capa');
    const foco      = $('tour-foco');
    const globo     = $('tour-globo');

    const PASOS = [
        { sel: '#panel-filtros', pos: 'derecha',
          titulo: 'Panel de consulta',
          texto: 'Todo empieza aquí. Los filtros se combinan entre sí y el mapa se actualiza al instante. Puedes cerrar el panel con la X y volver a abrirlo con el botón del borde izquierdo.',
          antes: abrirPanelFiltros },
        { sel: '#dd-tipo', pos: 'derecha',
          titulo: '1. ¿Qué información buscas?',
          texto: 'Elige uno o varios tipos de dato: pasivos ambientales mineros, derechos de uso de agua, puntos de monitoreo, residuos sólidos y más. Algunos tipos abren filtros extra, como el nivel de riesgo de los pasivos mineros.' },
        { sel: '#dd-cuenca', pos: 'derecha',
          titulo: '2. ¿En qué unidad hidrográfica?',
          texto: 'Filtra por cuenca. Al seleccionar una, aparece un filtro adicional de subcuencas para acercarte todavía más al territorio que te interesa.' },
        { sel: '#dd-provincia', pos: 'derecha',
          titulo: '3. Provincia y distrito',
          texto: 'Acota por división política. Solo se ofrecen las 20 provincias y los distritos de Áncash, y las opciones se van reduciendo según lo que ya elegiste.' },
        { sel: '#slider-cuenca', pos: 'derecha',
          titulo: 'Transparencia de cada capa',
          texto: 'Cada límite dibujado tiene su propio control de transparencia. Súbelo para resaltar el polígono o bájalo para ver mejor el mapa de fondo.' },
        { sel: '#toggle-cluster', pos: 'derecha',
          titulo: 'Agrupar puntos',
          texto: 'Cuando hay muchos registros, se agrupan en círculos que muestran cuántos puntos contiene cada zona. Haz clic en un grupo para acercarte, o desactiva la casilla para ver los puntos uno a uno.' },
        { sel: '#contador-resultados', pos: 'derecha',
          titulo: 'Resultados y descarga',
          texto: 'Aquí ves cuántos registros cumplen tus filtros. El botón de descarga te entrega exactamente esos datos en formato CSV, listos para Excel.' },
        { sel: '#ctrl-tematicas', pos: 'izquierda',
          titulo: 'Explorar por temática',
          texto: 'Si no sabes por dónde empezar, este botón te propone recorridos ya armados sobre agua, minería, residuos sólidos y metales pesados, con un dato destacado en cada paso.' },
        { sel: '#controles-flotantes', pos: 'izquierda',
          titulo: 'Mapa base, capas e iniciativas',
          texto: 'Cambia el fondo del mapa entre calles, satélite, relieve u oscuro; activa capas como la red hídrica o el Área de Conservación Regional; y consulta las iniciativas forestales de la región.' },
        { sel: '#mapa', pos: 'centro',
          titulo: 'El mapa es interactivo',
          texto: 'Haz clic en cualquier punto para abrir su ficha completa: entidad responsable, ubicación y todos los atributos del registro original.' },
        { sel: '#chatbot-container', pos: 'arriba',
          titulo: 'Asistente de consulta',
          texto: 'Puedes preguntarle en lenguaje simple cuántos registros hay por provincia o por tipo de dato, sin tocar los filtros.' }
    ];

    let pasoActual = 0;
    let pasosVigentes = [];

    function abrirPanelFiltros() {
        const p = $('panel-filtros');
        if (p && p.style.display === 'none') {
            p.style.display = 'flex';
            const b = $('btn-abrir-panel');
            if (b) b.style.display = 'none';
        }
    }

    function visible(el) {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    function iniciarTour() {
        if (typeof abrirPanelFiltros === 'function') abrirPanelFiltros();
        // Se descartan los pasos cuyo elemento no exista o esté oculto
        pasosVigentes = PASOS.filter(p => {
            if (p.antes) p.antes();
            return visible(document.querySelector(p.sel));
        });
        if (!pasosVigentes.length) return;
        pasoActual = 0;
        capaTour.style.display = 'block';
        requestAnimationFrame(() => capaTour.classList.add('visible'));
        construirPuntos();
        mostrarPaso(0);
        document.addEventListener('keydown', teclasTour);
    }

    function cerrarTour() {
        capaTour.classList.remove('visible');
        setTimeout(() => { capaTour.style.display = 'none'; }, 260);
        document.removeEventListener('keydown', teclasTour);
    }

    function teclasTour(e) {
        if (e.key === 'Escape')     cerrarTour();
        if (e.key === 'ArrowRight') irAPaso(pasoActual + 1);
        if (e.key === 'ArrowLeft')  irAPaso(pasoActual - 1);
    }

    function construirPuntos() {
        const cont = $('tour-puntos');
        cont.innerHTML = '';
        pasosVigentes.forEach((_, i) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.setAttribute('aria-label', 'Paso ' + (i + 1));
            b.addEventListener('click', () => irAPaso(i));
            cont.appendChild(b);
        });
    }

    function irAPaso(i) {
        if (i < 0) return;
        if (i >= pasosVigentes.length) { cerrarTour(); return; }
        mostrarPaso(i);
    }

    function mostrarPaso(i) {
        pasoActual = i;
        const paso = pasosVigentes[i];
        if (paso.antes) paso.antes();

        const el = document.querySelector(paso.sel);
        if (!el) { irAPaso(i + 1); return; }

        const r = el.getBoundingClientRect();
        const m = 8;   // margen del foco alrededor del elemento

        // Recuadro de foco
        foco.style.top    = (r.top - m) + 'px';
        foco.style.left   = (r.left - m) + 'px';
        foco.style.width  = (r.width + m * 2) + 'px';
        foco.style.height = (r.height + m * 2) + 'px';

        // Contenido del globo
        $('tour-titulo').textContent  = paso.titulo;
        $('tour-texto').textContent   = paso.texto;
        $('tour-paso-num').textContent = `${i + 1} / ${pasosVigentes.length}`;
        $('tour-siguiente').innerHTML = (i === pasosVigentes.length - 1)
            ? 'Empezar a explorar <i class="fa-solid fa-check"></i>'
            : 'Siguiente <i class="fa-solid fa-arrow-right"></i>';
        $('tour-anterior').style.visibility = i === 0 ? 'hidden' : 'visible';

        Array.from($('tour-puntos').children)
             .forEach((b, k) => b.classList.toggle('activo', k === i));

        // Posición del globo (se mide después de pintar el texto)
        requestAnimationFrame(() => {
            const g = globo.getBoundingClientRect();
            const sep = 18;
            let top, left;

            switch (paso.pos) {
                case 'derecha':
                    left = r.right + sep;
                    top  = r.top + r.height / 2 - g.height / 2;
                    break;
                case 'izquierda':
                    left = r.left - g.width - sep;
                    top  = r.top + r.height / 2 - g.height / 2;
                    break;
                case 'arriba':
                    left = r.left + r.width / 2 - g.width / 2;
                    top  = r.top - g.height - sep;
                    break;
                default:  // centro
                    left = window.innerWidth / 2 - g.width / 2;
                    top  = window.innerHeight / 2 - g.height / 2;
            }
            // Si no cabe a la derecha, se voltea a la izquierda y viceversa
            if (left + g.width > window.innerWidth - 12) left = r.left - g.width - sep;
            if (left < 12) left = Math.min(r.right + sep, window.innerWidth - g.width - 12);

            globo.style.left = Math.max(12, Math.min(left, window.innerWidth  - g.width  - 12)) + 'px';
            globo.style.top  = Math.max(12, Math.min(top,  window.innerHeight - g.height - 12)) + 'px';
        });
    }

    $('tour-cerrar').addEventListener('click', cerrarTour);
    $('tour-siguiente').addEventListener('click', () => irAPaso(pasoActual + 1));
    $('tour-anterior').addEventListener('click', () => irAPaso(pasoActual - 1));
    $('ctrl-ayuda').addEventListener('click', iniciarTour);
    window.addEventListener('resize', () => {
        if (capaTour.classList.contains('visible')) mostrarPaso(pasoActual);
    });

    /* ══════════════════════════════════════════════════════════════════════
       3. TEMÁTICAS Y PRESETS
       ══════════════════════════════════════════════════════════════════════ */
    const selector  = $('tema-selector');
    const ventana   = $('tema-dato');
    let TEMAS       = [];
    let temaActivo  = null;
    let presetIdx   = 0;

    fetch(API + '/api/tematicas')
        .then(r => r.json())
        .then(d => { TEMAS = d.tematicas || []; pintarSelector(); })
        .catch(e => console.warn('Temáticas:', e));

    function pintarSelector() {
        const cont = $('tema-sel-lista');
        cont.innerHTML = '';
        TEMAS.forEach(t => {
            const card = document.createElement('button');
            card.type = 'button';
            card.className = 'tema-card';
            card.style.setProperty('--c', t.color);
            card.innerHTML = `
                <span class="tema-card-icono"><i class="fa-solid ${t.icono}"></i></span>
                <span class="tema-card-texto">
                    <span class="tema-card-nombre">${t.nombre}</span>
                    <span class="tema-card-desc">${t.descripcion}</span>
                </span>
                <span class="tema-card-cifra">${t.total.toLocaleString('es-PE')}</span>`;
            card.addEventListener('click', () => abrirTema(t.id));
            cont.appendChild(card);
        });
    }

    function toggleSelector() {
        const abierto = selector.classList.contains('visible');
        selector.classList.toggle('visible', !abierto);
        $('ctrl-tematicas').classList.toggle('activo', !abierto);
    }

    $('ctrl-tematicas').addEventListener('click', toggleSelector);
    $('tema-sel-cerrar').addEventListener('click', () => {
        selector.classList.remove('visible');
        $('ctrl-tematicas').classList.remove('activo');
    });
    $('td-cerrar').addEventListener('click', () => ventana.classList.remove('visible'));

    function abrirTema(id) {
        temaActivo = TEMAS.find(t => t.id === id);
        if (!temaActivo || !temaActivo.presets.length) return;
        selector.classList.remove('visible');
        $('ctrl-tematicas').classList.remove('activo');
        presetIdx = 0;
        ventana.classList.add('visible');
        construirPuntosPreset();
        mostrarPreset(0);
    }

    function construirPuntosPreset() {
        const cont = $('td-puntos');
        cont.innerHTML = '';
        temaActivo.presets.forEach((_, i) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.setAttribute('aria-label', 'Dato ' + (i + 1));
            b.addEventListener('click', () => mostrarPreset(i));
            cont.appendChild(b);
        });
    }

    function mostrarPreset(i) {
        const n = temaActivo.presets.length;
        presetIdx = ((i % n) + n) % n;              // navegación circular
        const p = temaActivo.presets[presetIdx];

        ventana.style.setProperty('--c', temaActivo.color);
        $('td-barra').style.background = temaActivo.color;
        $('td-tema').querySelector('span').textContent = temaActivo.nombre;
        $('td-tema').querySelector('i').className = 'fa-solid ' + temaActivo.icono;
        $('td-valor').textContent   = p.metrica.valor;
        $('td-unidad').textContent  = p.metrica.unidad;
        $('td-titulo').textContent  = p.titulo;
        $('td-dato').innerHTML      = p.dato;
        const det = $('td-detalle');
        det.textContent = p.detalle || '';
        det.style.display = p.detalle ? 'block' : 'none';

        Array.from($('td-puntos').children)
             .forEach((b, k) => b.classList.toggle('activo', k === presetIdx));

        aplicarPreset(p.filtros);
    }

    $('td-siguiente').addEventListener('click', () => mostrarPreset(presetIdx + 1));
    $('td-anterior').addEventListener('click', () => mostrarPreset(presetIdx - 1));
    document.addEventListener('keydown', e => {
        if (!ventana.classList.contains('visible')) return;
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === 'ArrowRight') mostrarPreset(presetIdx + 1);
        if (e.key === 'ArrowLeft')  mostrarPreset(presetIdx - 1);
        if (e.key === 'Escape')     ventana.classList.remove('visible');
    });

    /* ── Aplicación de un preset sobre los filtros existentes ─────────────── */
    function valoresDisponibles(idLista) {
        return Array.from(document.querySelectorAll(`#${idLista} input`)).map(cb => cb.value);
    }
    function normal(t) {
        return String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/\s+/g, ' ').trim().toUpperCase();
    }
    function coincidencias(pedidos, disponibles) {
        const mapa = new Map(disponibles.map(v => [normal(v), v]));
        return pedidos.map(p => mapa.get(normal(p))).filter(Boolean);
    }

    async function aplicarPreset(filtros) {
        try {
            const tiposDisp = valoresDisponibles('filtro-tipo');
            if (!tiposDisp.length) return;   // los filtros aún no han cargado

            selecciones.tipo       = coincidencias(filtros.tipo || [], tiposDisp);
            selecciones.cuenca     = (filtros.cuenca || []).slice();
            selecciones.provincia  = (filtros.provincia || []).slice();
            selecciones.distrito   = (filtros.distrito || []).slice();
            selecciones.subcuenca  = [];
            selecciones.secundarios = {};

            llenarChecklist('filtro-tipo', tiposDisp, selecciones.tipo);

            // Filtros específicos del tipo (por ejemplo RIESGO en pasivos mineros)
            await actualizarFiltrosSecundarios(selecciones.tipo);
            const sec = filtros.secundarios || {};
            for (const col in sec) {
                const caja = document.getElementById(`filtro-sec-${col}`);
                if (!caja) continue;
                const marcados = [];
                caja.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    const activo = sec[col].some(v => normal(v) === normal(cb.value));
                    cb.checked = activo;
                    if (activo) marcados.push(cb.value);
                });
                selecciones.secundarios[col] = marcados;
                const dd = document.getElementById(`dd-sec-${col}`);
                const anchor = dd && dd.querySelector('.anchor');
                if (anchor) anchor.innerText = marcados.length === 0 ? 'Seleccione...'
                    : marcados.length === 1 ? marcados[0] : `${marcados.length} seleccionados`;
            }

            if (typeof actualizarFiltrosSubcuenca === 'function')
                await actualizarFiltrosSubcuenca(selecciones.cuenca);

            await triggerCascada();
            aplicarFiltros();
        } catch (e) {
            console.warn('No se pudo aplicar el preset:', e);
        }
    }
})();
