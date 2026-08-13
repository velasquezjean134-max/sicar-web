/* ═══════════════════════════════════════════════════════════════════════════
   SICAR Áncash — Perfiles de usuario
   ───────────────────────────────────────────────────────────────────────────
   Primera pantalla del visor: pregunta desde qué perfil navega la persona y
   adapta la interfaz en consecuencia. Se ejecuta ANTES de la bienvenida, a la
   que llama cuando el perfil ya está definido.

   Principio de diseño: simplificar no es bloquear. Los perfiles no técnicos
   ven un panel más limpio, pero conservan el botón «Ver herramientas
   avanzadas», que restituye la interfaz completa. Ningún dato queda vedado.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    const CLAVE = 'sicar_perfil_v1';
    const $ = id => document.getElementById(id);

    /* ══════════════════════════════════════════════════════════════════════
       Definición de los perfiles
       ══════════════════════════════════════════════════════════════════════ */
    const PERFILES = [
        {
            id: 'ciudadania',
            nombre: 'Ciudadanía y organizaciones sociales',
            corto: 'Ciudadanía',
            icono: 'fa-people-group',
            color: '#2e8b57',
            descripcion: 'Quiero entender qué pasa con el ambiente en mi distrito',
            // Elementos que se retiran del panel para este perfil
            oculta: ['tipo', 'secundarios', 'subcuenca', 'sliders', 'cluster', 'csv'],
            alEntrar: 'tematicas'   // abre el explorador temático automáticamente
        },
        {
            id: 'autoridad',
            nombre: 'Autoridad regional o local',
            corto: 'Autoridad',
            icono: 'fa-landmark',
            color: '#0182c7',
            descripcion: 'Necesito evidencia para decidir y reportar',
            oculta: ['secundarios', 'subcuenca', 'sliders'],
            alEntrar: null
        },
        {
            id: 'tecnico',
            nombre: 'Técnico de entidad pública',
            corto: 'Técnico',
            icono: 'fa-drafting-compass',
            color: '#7c3aed',
            descripcion: 'Trabajo con los datos y necesito el detalle completo',
            oculta: [],
            alEntrar: null
        },
        {
            id: 'privado',
            nombre: 'Profesional del sector privado',
            corto: 'Sector privado',
            icono: 'fa-briefcase',
            color: '#a8730f',
            descripcion: 'Requiero información ambiental del área donde opero',
            oculta: [],
            alEntrar: null
        }
    ];

    /* Mensaje de contexto que se muestra al entrar, según el perfil */
    const CONTEXTO = {
        ciudadania: 'Elige tu provincia y distrito para ver qué información ambiental existe en tu zona.',
        autoridad:  'Selecciona un ámbito territorial y descarga el informe en PDF con el panorama completo.',
        tecnico:    'Panel completo habilitado: filtros por tipo, cuenca, subcuenca y filtros específicos.',
        privado:    'Consulta pasivos ambientales, calidad del agua y unidades fiscalizables por ámbito.'
    };

    const overlay = $('perfil-overlay');
    const cont    = $('pf-opciones');
    if (!overlay || !cont) return;

    /* ══════════════════════════════════════════════════════════════════════
       Marcado de los elementos que se ocultan por perfil
       ══════════════════════════════════════════════════════════════════════ */
    function marcarElementos() {
        const marca = (el, clase) => { if (el) el.classList.add(clase); };

        // 1. Filtro de tipo de información (y su etiqueta)
        const ddTipo = $('dd-tipo');
        marca(ddTipo, 'req-tipo');
        if (ddTipo && ddTipo.previousElementSibling)
            marca(ddTipo.previousElementSibling, 'req-tipo');

        // 2. Filtros específicos que aparecen según el tipo
        marca($('contenedor-filtros-secundarios'), 'req-secundarios');

        // 3. Bloque de subcuencas
        marca($('contenedor-filtro-subcuenca'), 'req-subcuenca');

        // 4. Controles de transparencia
        document.querySelectorAll('.slider-mini').forEach(s => marca(s, 'req-sliders'));

        // 5. Interruptor de agrupación de puntos (su fila completa)
        const tc = $('toggle-cluster');
        if (tc) {
            const fila = tc.closest('.filtro-header');
            marca(fila || tc, 'req-cluster');
        }

        // 6. Descarga CSV
        marca($('btn-descargar-csv'), 'req-csv');
    }

    /* ══════════════════════════════════════════════════════════════════════
       Aplicación del perfil
       ══════════════════════════════════════════════════════════════════════ */
    function aplicar(perfil, esCambio) {
        window.SICAR_PERFIL = perfil.id;

        // Clases en <body>: perfil activo + qué se oculta
        document.body.className = document.body.className
            .replace(/\bperfil-\S+/g, '')
            .replace(/\boculta-\S+/g, '')
            .trim();
        document.body.classList.add('perfil-' + perfil.id);
        perfil.oculta.forEach(o => document.body.classList.add('oculta-' + o));
        document.body.classList.remove('modo-avanzado');

        // Distintivo en el panel
        const chip = $('chip-perfil');
        if (chip) {
            chip.style.setProperty('--c', perfil.color);
            const ic = chip.querySelector('.chip-icono i');
            if (ic) ic.className = 'fa-solid ' + perfil.icono;
            const nb = $('chip-perfil-nombre');
            if (nb) nb.textContent = perfil.corto;
            chip.title = perfil.nombre;
        }

        // Botón de herramientas avanzadas: solo si hay algo simplificado
        const btnAv = $('btn-modo-avanzado');
        if (btnAv) btnAv.style.display = perfil.oculta.length ? 'flex' : 'none';

        // Mensaje de contexto en el aviso de bienvenida del visor
        const toast = $('toast-bienvenida');
        if (toast && CONTEXTO[perfil.id]) {
            toast.innerHTML = `👋 <strong>${perfil.corto}</strong>. ${CONTEXTO[perfil.id]}`;
            if (esCambio) {
                toast.style.display = 'block';
                toast.style.opacity = '1';
                setTimeout(() => {
                    toast.style.opacity = '0';
                    setTimeout(() => { toast.style.display = 'none'; }, 500);
                }, 5000);
            }
        }

        try { localStorage.setItem(CLAVE, perfil.id); } catch (e) {}
    }

    function porId(id) {
        return PERFILES.find(p => p.id === id) || null;
    }

    /* ══════════════════════════════════════════════════════════════════════
       Pantalla de selección
       ══════════════════════════════════════════════════════════════════════ */
    function pintar() {
        cont.innerHTML = '';
        PERFILES.forEach(p => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'pf-opcion';
            b.style.setProperty('--c', p.color);
            b.innerHTML = `
                <span class="pf-op-icono"><i class="fa-solid ${p.icono}"></i></span>
                <span class="pf-op-texto">
                    <span class="pf-op-nombre">${p.nombre}</span>
                    <span class="pf-op-desc">${p.descripcion}</span>
                </span>
                <span class="pf-op-flecha"><i class="fa-solid fa-arrow-right"></i></span>`;
            b.addEventListener('click', () => elegir(p));
            cont.appendChild(b);
        });
    }

    function mostrarSelector() {
        pintar();
        overlay.style.display = 'flex';
        requestAnimationFrame(() => overlay.classList.add('visible'));
    }

    function ocultarSelector() {
        overlay.classList.remove('visible');
        setTimeout(() => { overlay.style.display = 'none'; }, 300);
    }

    let primeraVez = true;

    function elegir(perfil) {
        const cambio = !primeraVez;
        aplicar(perfil, cambio);
        ocultarSelector();

        if (primeraVez) {
            primeraVez = false;
            // Encadena con la bienvenida ya existente
            setTimeout(() => {
                if (window.SICAR_UI && window.SICAR_UI.mostrarBienvenida)
                    window.SICAR_UI.mostrarBienvenida();
            }, 340);
        }

        // Acción de entrada propia del perfil
        if (perfil.alEntrar === 'tematicas') {
            setTimeout(() => {
                const b = $('bienvenida-overlay');
                const abierta = b && b.classList.contains('visible');
                const t = $('tour-capa');
                const enTour = t && t.classList.contains('visible');
                if (!abierta && !enTour && window.SICAR_UI && window.SICAR_UI.abrirTematicas)
                    window.SICAR_UI.abrirTematicas();
            }, 1200);
        }
    }

    /* ══════════════════════════════════════════════════════════════════════
       Arranque
       ══════════════════════════════════════════════════════════════════════ */
    marcarElementos();

    let guardado = null;
    try { guardado = localStorage.getItem(CLAVE); } catch (e) {}
    const previo = guardado ? porId(guardado) : null;

    if (previo) {
        // Ya eligió antes: se aplica directo y se pasa a la bienvenida
        primeraVez = false;
        aplicar(previo, false);
        overlay.style.display = 'none';
        setTimeout(() => {
            if (window.SICAR_UI && window.SICAR_UI.mostrarBienvenida)
                window.SICAR_UI.mostrarBienvenida();
        }, 120);
    } else {
        mostrarSelector();
    }

    /* Cambio de perfil desde el distintivo del panel */
    const btnCambiar = $('chip-cambiar');
    if (btnCambiar) btnCambiar.addEventListener('click', mostrarSelector);

    /* Herramientas avanzadas */
    const btnAv = $('btn-modo-avanzado');
    if (btnAv) {
        btnAv.addEventListener('click', () => {
            const activo = document.body.classList.toggle('modo-avanzado');
            btnAv.querySelector('span').textContent = activo
                ? 'Volver a la vista simple'
                : 'Ver herramientas avanzadas';
            btnAv.classList.toggle('activo', activo);
        });
    }

    /* Permite cerrar el selector con Esc solo si ya hay un perfil aplicado */
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && overlay.classList.contains('visible') && window.SICAR_PERFIL)
            ocultarSelector();
    });
    overlay.addEventListener('click', e => {
        if (e.target === overlay && window.SICAR_PERFIL) ocultarSelector();
    });
})();
