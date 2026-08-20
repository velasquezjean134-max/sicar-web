/* ═══════════════════════════════════════════════════════════════════════════
   SICAR Áncash — Pantalla de carga
   ───────────────────────────────────────────────────────────────────────────
   El servidor de datos se suspende tras periodos de inactividad y puede tardar
   cerca de un minuto en reactivarse. Sin aviso, esa espera se interpreta como
   que el visor no funciona. Esta pantalla cubre la interfaz hasta que los
   filtros estén cargados, explica lo que ocurre y evita que se interactúe con
   un visor a medio preparar.

   Módulo independiente: no modifica ninguna función existente. Detecta que el
   visor está listo observando el DOM, sin acoplarse a script.js.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    const overlay   = document.getElementById('carga-overlay');
    if (!overlay) return;

    const elMensaje = document.getElementById('carga-mensaje');
    const elNota    = document.getElementById('carga-nota');
    const elBarra   = document.getElementById('carga-progreso');
    const btnRetry  = document.getElementById('carga-reintentar');

    const INICIO      = Date.now();
    const LIMITE_MS   = 120000;   // a los 2 minutos se ofrece reintentar
    let   terminado   = false;

    /* Mensajes que acompañan la espera según cuánto lleva */
    const FASES = [
        { desde: 0,     mensaje: 'Preparando el visor…',
          nota: '' },
        { desde: 4000,  mensaje: 'Conectando con el servidor de datos…',
          nota: '' },
        { desde: 11000, mensaje: 'Reactivando el servidor',
          nota: 'El servicio se suspende tras periodos de inactividad. La primera consulta puede tomar hasta un minuto. Gracias por esperar.' },
        { desde: 45000, mensaje: 'Casi listo',
          nota: 'El servidor está terminando de iniciar. La espera solo ocurre en la primera visita del día.' },
        { desde: 80000, mensaje: 'La conexión está tardando más de lo habitual',
          nota: 'Puedes seguir esperando o reintentar. Si el problema persiste, vuelve a intentarlo en unos minutos.' }
    ];

    function transcurrido() { return Date.now() - INICIO; }

    function pintar() {
        if (terminado) return;
        const t = transcurrido();

        // Mensaje correspondiente a la fase actual
        let fase = FASES[0];
        for (const f of FASES) if (t >= f.desde) fase = f;
        if (elMensaje.textContent !== fase.mensaje) elMensaje.textContent = fase.mensaje;
        if (elNota.textContent !== fase.nota) {
            elNota.textContent = fase.nota;
            elNota.style.opacity = fase.nota ? '1' : '0';
        }

        // Barra de avance: rápida al inicio y cada vez más lenta, sin llegar
        // nunca al 100 % hasta que los datos realmente estén disponibles.
        const pct = Math.min(94, 100 * (1 - Math.exp(-t / 22000)));
        elBarra.style.width = pct.toFixed(1) + '%';

        if (t > LIMITE_MS) btnRetry.classList.add('visible');
    }

    /* ── ¿Está listo el visor? ──────────────────────────────────────────────
       Se considera listo cuando el desplegable de tipos de información ya tiene
       opciones: eso significa que /api/filtros respondió y el visor se pobló. */
    function visorListo() {
        const lista = document.getElementById('filtro-tipo');
        return !!(lista && lista.querySelector('input'));
    }

    function cerrar() {
        if (terminado) return;
        terminado = true;
        elBarra.style.width = '100%';
        elMensaje.textContent = 'Listo';
        overlay.classList.add('oculto');
        setTimeout(() => { overlay.style.display = 'none'; }, 520);
        document.body.classList.remove('cargando');
    }

    document.body.classList.add('cargando');

    const reloj = setInterval(() => {
        pintar();
        if (visorListo()) {
            clearInterval(reloj);
            // Pequeña pausa para que la transición no se sienta brusca
            setTimeout(cerrar, 320);
        }
    }, 200);

    btnRetry.addEventListener('click', () => location.reload());

    /* Salvavidas: si algo fallara y el visor nunca reportara estar listo,
       la pantalla se retira igualmente para no dejar la página bloqueada. */
    setTimeout(() => {
        if (!terminado) {
            clearInterval(reloj);
            elNota.textContent = 'Algunos datos podrían no haberse cargado. Si el visor se ve incompleto, recarga la página.';
            btnRetry.classList.add('visible');
            setTimeout(cerrar, 4000);
        }
    }, 180000);
})();
