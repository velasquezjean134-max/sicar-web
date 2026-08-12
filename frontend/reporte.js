/* ═══════════════════════════════════════════════════════════════════════════
   SICAR Áncash — Descarga de reporte PDF por ámbito territorial
   ───────────────────────────────────────────────────────────────────────────
   Módulo independiente. No modifica funciones existentes: solo lee la variable
   global `selecciones` de script.js y observa el botón de descarga CSV para
   mostrarse u ocultarse en sincronía con él.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    const $ = id => document.getElementById(id);
    const btn      = $('btn-descargar-reporte');
    const overlay  = $('reporte-overlay');
    const contOpc  = $('rp-opciones');
    const estado   = $('rp-estado');
    const btnCsv   = $('btn-descargar-csv');

    if (!btn || !overlay) return;

    const ICONOS = { distrito: 'fa-map-pin', provincia: 'fa-map-location-dot', cuenca: 'fa-water' };
    const COLORES = { distrito: '#2ca02c', provincia: '#ff7f0e', cuenca: '#0068c9' };
    const ETIQUETAS = { distrito: 'Distrito', provincia: 'Provincia', cuenca: 'Unidad hidrográfica' };
    // Del ámbito más específico al más amplio
    const ORDEN = ['distrito', 'provincia', 'cuenca'];

    /* ── Ámbitos disponibles según los filtros activos ────────────────────── */
    function ambitosDisponibles() {
        const lista = [];
        if (typeof selecciones === 'undefined') return lista;
        ORDEN.forEach(amb => {
            (selecciones[amb] || []).forEach(valor => lista.push({ ambito: amb, valor }));
        });
        return lista;
    }

    /* ── El botón acompaña al de CSV ──────────────────────────────────────── */
    function actualizarVisibilidad() {
        const hayResultados = btnCsv && btnCsv.style.display !== 'none';
        const hayAmbito = ambitosDisponibles().length > 0;
        btn.style.display = (hayResultados && hayAmbito) ? 'flex' : 'none';
    }

    // El botón CSV se muestra u oculta desde aplicarFiltros(); se observa su
    // atributo style para reaccionar sin tocar esa función.
    if (btnCsv) {
        new MutationObserver(actualizarVisibilidad)
            .observe(btnCsv, { attributes: true, attributeFilter: ['style'] });
    }
    setInterval(actualizarVisibilidad, 1200);   // red de seguridad
    actualizarVisibilidad();

    /* ── Ventana de selección ─────────────────────────────────────────────── */
    function abrir() {
        const opciones = ambitosDisponibles();
        contOpc.innerHTML = '';
        estado.innerHTML = '';
        estado.className = '';

        if (!opciones.length) {
            contOpc.innerHTML = `<p class="rp-vacio">
                Selecciona al menos un distrito, una provincia o una cuenca en los filtros
                para poder generar el reporte.</p>`;
        } else {
            opciones.forEach(o => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'rp-opcion';
                b.style.setProperty('--c', COLORES[o.ambito]);
                b.innerHTML = `
                    <span class="rp-op-icono"><i class="fa-solid ${ICONOS[o.ambito]}"></i></span>
                    <span class="rp-op-texto">
                        <span class="rp-op-ambito">${ETIQUETAS[o.ambito]}</span>
                        <span class="rp-op-valor">${o.valor}</span>
                    </span>
                    <span class="rp-op-flecha"><i class="fa-solid fa-download"></i></span>`;
                b.addEventListener('click', () => descargar(o, b));
                contOpc.appendChild(b);
            });
        }
        overlay.classList.add('visible');
    }

    function cerrar() { overlay.classList.remove('visible'); }

    btn.addEventListener('click', abrir);
    $('rp-cerrar').addEventListener('click', cerrar);
    overlay.addEventListener('click', e => { if (e.target === overlay) cerrar(); });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && overlay.classList.contains('visible')) cerrar();
    });

    /* ── Descarga ─────────────────────────────────────────────────────────── */
    async function descargar(opcion, boton) {
        const previo = boton.innerHTML;
        boton.classList.add('cargando');
        boton.innerHTML = `<span class="rp-op-icono"><i class="fa-solid fa-spinner fa-spin"></i></span>
            <span class="rp-op-texto"><span class="rp-op-ambito">Generando informe…</span>
            <span class="rp-op-valor">${opcion.valor}</span></span>`;
        estado.className = '';
        estado.innerHTML = '';

        try {
            const r = await fetch(API + '/api/reporte', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(opcion)
            });

            if (!r.ok) {
                let msg = `El servidor respondió ${r.status}.`;
                try { const j = await r.json(); if (j.detail) msg = j.detail; } catch (e) {}
                throw new Error(msg);
            }

            const blob = await r.blob();
            // Nombre sugerido por el servidor, si viene en la cabecera
            let nombre = `Reporte_SICAR_${opcion.ambito}_${opcion.valor}.pdf`.replace(/\s+/g, '_');
            const cd = r.headers.get('content-disposition');
            if (cd) {
                const m = cd.match(/filename="?([^"]+)"?/);
                if (m) nombre = m[1];
            }

            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = nombre;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 4000);

            estado.className = 'rp-ok';
            estado.innerHTML = `<i class="fa-solid fa-circle-check"></i> Reporte descargado.`;
            setTimeout(cerrar, 1400);
        } catch (e) {
            estado.className = 'rp-error';
            estado.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> No se pudo generar el reporte. ${e.message}`;
        } finally {
            boton.classList.remove('cargando');
            boton.innerHTML = previo;
        }
    }
})();
