// =============================================================================
// SICAR Áncash — script.js
// Arquitectura: CSV índice + CSVs detalle por dataset
// =============================================================================

const API = 'https://sicar-web-api.onrender.com';

// ── 1. MAPA ───────────────────────────────────────────────────────────────────
var mapa = L.map('mapa', { zoomControl: false }).setView([-9.52, -77.52], 8);
L.control.zoom({ position: 'bottomright' }).addTo(mapa);

var baseMaps = {
    "Claro":       L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap'}),
    "Topográfico": L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenTopoMap',maxZoom:17}),
    "Relieve":     L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}',{attribution:'&copy; Esri',maxZoom:13}),
    "Google Maps": L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',{attribution:'&copy; Google',maxNativeZoom:18,maxZoom:22}),
    "Satélite":    L.tileLayer('https://mt1.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}',{attribution:'&copy; Google',maxNativeZoom:18,maxZoom:22}),
    "Oscuro":      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'&copy; CartoDB',maxZoom:20}),
};
baseMaps["Claro"].addTo(mapa);

// Control de capas base — colapsable por defecto
//L.control.layers(baseMaps, {}, { position: 'topright', collapsed: true }).addTo(mapa);

// Panes z-index
['paneBase','paneCuencas','paneACR','paneRios','paneProvincias','paneDistritos','paneSubcuencas','panePuntos','paneIniciativas']
    .forEach((p,i) => { mapa.createPane(p); mapa.getPane(p).style.zIndex = 390 + i*10; });

var capaCuencas          = L.layerGroup().addTo(mapa);
var capaProvincias       = L.layerGroup().addTo(mapa);
var capaDistritos        = L.layerGroup().addTo(mapa);
var capaSubcuencas       = L.layerGroup().addTo(mapa);
var capaIniciativas      = L.layerGroup().addTo(mapa);
var capaCapasExternas    = {};   // id -> L.layerGroup
// ── Agrupación de puntos (clustering) ─────────────────────────────────────────
// Escalas por volumen: cada rango tiene su tamaño y su color, con un anillo de
// progreso que indica qué tan denso es el grupo respecto al total agrupado.
const ESCALAS_CLUSTER = [
    { max:   9, clase:'cl-xs', d:36 },
    { max:  49, clase:'cl-sm', d:42 },
    { max: 199, clase:'cl-md', d:50 },
    { max: 999, clase:'cl-lg', d:58 },
    { max: Infinity, clase:'cl-xl', d:66 }
];

function formatearConteo(n){
    if(n >= 1000) return (n/1000).toFixed(n >= 10000 ? 0 : 1).replace('.0','') + 'k';
    return String(n);
}

function crearIconoCluster(cluster){
    const n = cluster.getChildCount();
    const esc = ESCALAS_CLUSTER.find(e => n <= e.max);
    const d = esc.d, r = (d/2) - 3;
    const circ = 2 * Math.PI * r;
    // Proporción logarítmica: evita que un grupo pequeño se vea casi vacío
    const prop = Math.min(Math.log10(n + 1) / 4, 1);

    const html = `
        <div class="cluster-sicar ${esc.clase}" style="width:${d}px;height:${d}px;">
            <svg class="cluster-anillo" width="${d}" height="${d}" viewBox="0 0 ${d} ${d}">
                <circle cx="${d/2}" cy="${d/2}" r="${r}" class="cluster-pista"/>
                <circle cx="${d/2}" cy="${d/2}" r="${r}" class="cluster-progreso"
                        stroke-dasharray="${(circ*prop).toFixed(1)} ${circ.toFixed(1)}"
                        transform="rotate(-90 ${d/2} ${d/2})"/>
            </svg>
            <span class="cluster-num">${formatearConteo(n)}</span>
        </div>`;

    return L.divIcon({
        html, className:'cluster-sicar-wrap',
        iconSize: L.point(d, d), iconAnchor: L.point(d/2, d/2)
    });
}

var capaPuntosCluster    = L.markerClusterGroup({
    chunkedLoading:true,
    spiderfyOnMaxZoom:true,
    showCoverageOnHover:false,
    zoomToBoundsOnClick:true,
    maxClusterRadius:58,
    disableClusteringAtZoom:15,
    clusterPane:'panePuntos',
    iconCreateFunction: crearIconoCluster,
    polygonOptions:{fillOpacity:0,stroke:false}
});
var capaPuntosIndividual = L.layerGroup();

fetch(API+'/api/poligonos/ancash').then(r=>r.json())
    .then(g=>L.geoJSON(g,{pane:'paneBase',interactive:false,
        style:{color:"#333",weight:2,dashArray:"5,5",fillOpacity:0}}).addTo(mapa));

// ── 2. DRAG HELPER ────────────────────────────────────────────────────────────
function hacerArrastrable(panel, handle) {
    let drag=false, ox=0, oy=0;
    handle.style.cursor = 'grab';
    handle.addEventListener('mousedown', e => {
        if (e.target.tagName==='BUTTON'||e.target.tagName==='INPUT') return;
        drag = true;
        const r = panel.getBoundingClientRect();
        ox = e.clientX - r.left; oy = e.clientY - r.top;
        handle.style.cursor = 'grabbing';
        // Convertir a posición fija para mover libremente
        panel.style.position = 'fixed';
        panel.style.right = 'auto'; panel.style.bottom = 'auto';
        panel.style.left = r.left+'px'; panel.style.top = r.top+'px';
        e.preventDefault();
    });
    document.addEventListener('mousemove', e => {
        if (!drag) return;
        let nx = e.clientX-ox, ny = e.clientY-oy;
        nx = Math.max(0, Math.min(nx, window.innerWidth  - panel.offsetWidth));
        ny = Math.max(0, Math.min(ny, window.innerHeight - panel.offsetHeight));
        panel.style.left = nx+'px'; panel.style.top = ny+'px';
    });
    document.addEventListener('mouseup', () => { drag=false; handle.style.cursor='grab'; });
}

// ── 3. CONTROLES FLOTANTES ────────────────────────────────────────────────────
const menus = { mapas: 'menu-mapas', capas: 'menu-capas' };

function toggleCtrl(id) {
    const menu = document.getElementById(menus[id]);
    const btn  = document.getElementById('ctrl-' + id);
    const abierto = menu.classList.contains('visible');
    // Cerrar todos
    Object.values(menus).forEach(m => document.getElementById(m).classList.remove('visible'));
    document.querySelectorAll('.ctrl-btn').forEach(b => b.classList.remove('activo'));
    if (!abierto) {
        menu.classList.add('visible');
        btn.classList.add('activo');
        // Posicionar menú a la altura del botón
        const rect = btn.getBoundingClientRect();
        const cont = document.getElementById('controles-flotantes').getBoundingClientRect();
        menu.style.top = (rect.top - cont.top) + 'px';
    }
}

document.getElementById('ctrl-mapas')?.addEventListener('click', () => toggleCtrl('mapas'));
document.getElementById('ctrl-capas')?.addEventListener('click', () => toggleCtrl('capas'));

// Cambio de mapa base
document.querySelectorAll('input[name="mapaBase"]').forEach(r => {
    r.addEventListener('change', () => {
        Object.values(baseMaps).forEach(l => mapa.removeLayer(l));
        baseMaps[r.value]?.addTo(mapa);
    });
});

// Cerrar al click fuera
document.addEventListener('click', e => {
    if (!e.target.closest('#controles-flotantes')) {
        Object.values(menus).forEach(m => document.getElementById(m).classList.remove('visible'));
        document.querySelectorAll('.ctrl-btn').forEach(b => b.classList.remove('activo'));
    }
});

document.getElementById('toggle-iniciativas')?.addEventListener('change', e => {
    e.target.checked ? mapa.addLayer(capaIniciativas) : mapa.removeLayer(capaIniciativas);
});

// Cargar catálogo de capas
fetch(API+'/api/capas-externas').then(r=>r.json())
    .then(d => renderCapas(d.capas))
    .catch(() => { document.getElementById('lista-capas-externas').innerHTML='<p style="color:#e74c3c;font-size:11px;padding:5px;">Error cargando capas</p>'; });

// Botón iniciativas — abre el panel lateral
document.getElementById('ctrl-iniciativas')?.addEventListener('click', () => {
    document.querySelectorAll('.ctrl-btn').forEach(b => b.classList.remove('activo'));
    const panelIni = document.getElementById('panel-iniciativas');
    const abierto = panelIni.style.display === 'flex';
    panelIni.style.display = abierto ? 'none' : 'flex';
    document.getElementById('ctrl-iniciativas').classList.toggle('activo', !abierto);
    if (!abierto && !iniciativasCargadas) { iniciativasCargadas = true; cargarIniciativas(); }
});

// ── FUNCIÓN PARA RENDERIZAR LOS TOGGLES EN EL PANEL ──
function renderCapas(capas) {
    const contenedor = document.getElementById('lista-capas-externas');
    if (!contenedor) return;
    
    // Limpiar el texto de "Cargando..."
    contenedor.innerHTML = '';

    capas.forEach(capa => {
        // 1. Inicializar el LayerGroup vacío para esta capa en el mapa
        capaCapasExternas[capa.id] = L.layerGroup();

        // 2. Crear el elemento visual en el menú
        const item = document.createElement('div');
        item.className = 'capa-item';
        item.innerHTML = `
            <div class="capa-label" title="${capa.descripcion}">
                <i class="fa-solid ${capa.icono}" style="color:${capa.color};"></i>
                <span class="capa-nombre">${capa.nombre}</span>
            </div>
            <label class="switch">
                <input type="checkbox" id="toggle-${capa.id}">
                <span class="slider-toggle"></span>
            </label>
        `;
        contenedor.appendChild(item);

        // 3. Agregar el evento para prender/apagar la capa en Leaflet
        document.getElementById(`toggle-${capa.id}`).addEventListener('change', (e) => {
            if (e.target.checked) {
                mapa.addLayer(capaCapasExternas[capa.id]);
                cargarDatosCapa(capa); // Traer la data espacial si es la primera vez
            } else {
                mapa.removeLayer(capaCapasExternas[capa.id]);
            }
        });
    });
}

// ── FUNCIÓN PARA SOLICITAR Y DIBUJAR LA DATA ESPACIAL ──
async function cargarDatosCapa(capa) {
    const layerGroup = capaCapasExternas[capa.id];
    
    // Si ya descargamos la geometría antes, no volver a hacer la petición
    if (layerGroup.getLayers().length > 0) return;

    try {
        if (capa.tipo === 'geojson_local') {
            const res = await fetch(API + capa.endpoint);
            const geo = await res.json();
            
            L.geoJSON(geo, {
                style: {
                    color: capa.color,
                    fillColor: capa.fillColor || capa.color,
                    weight: capa.weight || 2,
                    fillOpacity: capa.fillOpacity || 0.2,
                    dashArray: capa.dashArray || ""
                }
            }).addTo(layerGroup);
            
        } else if (capa.tipo === 'osm_overpass') {
            // Ejemplo de llamada a la API de Overpass para los ríos
            const overpassUrl = 'https://overpass-api.de/api/interpreter';
            // Para overpass, reemplazamos (bbox) por el bounding box del mapa actual
            const bounds = mapa.getBounds();
            const bbox = `${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}`;
            const queryData = capa.query.replace('(bbox)', `(${bbox})`);
            
            const res = await fetch(overpassUrl, {
                method: 'POST',
                body: "data=" + encodeURIComponent(queryData)
            });
            const geo = await res.json();
            
            // Usar una librería externa como osmtogeojson o procesar los ways manualmente
            // Aquí se recomienda usar osmtogeojson si planeas trabajar con redes hidrográficas
            console.log("Datos Overpass recibidos:", geo);
        }
    } catch (error) {
        console.error(`Error cargando la geometría para la capa ${capa.id}:`, error);
    }
}

// ── 4. UI SICAR ───────────────────────────────────────────────────────────────
const panelFiltros = document.getElementById('panel-filtros');
document.getElementById('btn-cerrar-panel')?.addEventListener('click', () => {
    panelFiltros.style.display='none'; document.getElementById('btn-abrir-panel').style.display='block';
});
document.getElementById('btn-abrir-panel')?.addEventListener('click', () => {
    panelFiltros.style.display='flex'; document.getElementById('btn-abrir-panel').style.display='none';
});
document.getElementById('btn-cerrar-detalles')?.addEventListener('click', () =>
    document.getElementById('panel-detalles').style.display='none');

// Dropdowns
document.querySelectorAll('.dropdown-check-list .anchor').forEach(a => {
    a.onclick = function() {
        document.querySelectorAll('.dropdown-check-list').forEach(dd => {
            if (dd !== this.parentElement) dd.classList.remove('visible');
        });
        this.parentElement.classList.toggle('visible');
    };
});
document.addEventListener('click', e => {
    if (!e.target.closest('.dropdown-check-list'))
        document.querySelectorAll('.dropdown-check-list').forEach(dd => dd.classList.remove('visible'));
});

// Leyenda movible
const leyenda = document.getElementById('leyenda-mapa');
if (leyenda) {
    let d=false,ox=0,oy=0;
    leyenda.addEventListener('mousedown',e=>{d=true;ox=e.clientX-leyenda.getBoundingClientRect().left;oy=e.clientY-leyenda.getBoundingClientRect().top;leyenda.style.cursor='grabbing';});
    document.addEventListener('mousemove',e=>{if(d){leyenda.style.left=(e.clientX-ox)+'px';leyenda.style.top=(e.clientY-oy)+'px';leyenda.style.bottom='auto';}});
    document.addEventListener('mouseup',()=>{d=false;leyenda.style.cursor='move';});
}

setTimeout(()=>{const t=document.getElementById('toast-bienvenida');if(t){t.style.opacity='0';setTimeout(()=>t.style.display='none',500);}},4000);

// ── 5. FILTROS SICAR ──────────────────────────────────────────────────────────
let selecciones = {tipo:[],cuenca:[],subcuenca:[],provincia:[],distrito:[], secundarios:{}};

function getMarcados(id){ return Array.from(document.querySelectorAll(`#${id} input:checked`)).map(cb=>cb.value); }
function setAnchor(id,sel){
    const a=document.getElementById(id)?.parentElement?.querySelector('.anchor');
    if(a) a.innerText = sel.length===0?'Seleccione opciones...':sel.length===1?sel[0]:`${sel.length} seleccionados`;
}
function llenarChecklist(id,lista,sel){
    const c=document.getElementById(id); if(!c) return;
    c.innerHTML='';
    lista.forEach(op=>{
        const li=document.createElement('li');
        li.innerHTML=`<label><input type="checkbox" value="${op}" ${sel.includes(op)?'checked':''}> ${op}</label>`;
        c.appendChild(li);
    });
    c.querySelectorAll('input').forEach(cb=>cb.addEventListener('change',async()=>{
        selecciones.tipo=getMarcados('filtro-tipo');
        selecciones.cuenca=getMarcados('filtro-cuenca');
        selecciones.subcuenca=getMarcados('filtro-subcuenca');
        selecciones.provincia=getMarcados('filtro-provincia');
        selecciones.distrito=getMarcados('filtro-distrito');
        
        // Gatillar filtros secundarios si el cambio vino de "TIPO"
        if(id === 'filtro-tipo') {
            await actualizarFiltrosSecundarios(selecciones.tipo);
        }
        // Actualizar dropdown subcuencas si cambia la cuenca
        if(id === 'filtro-cuenca') {
            await actualizarFiltrosSubcuenca(selecciones.cuenca);
        }

        await triggerCascada(); aplicarFiltros();
    }));
    setAnchor(id,sel);
}
async function triggerCascada(){
    try{
        const r=await fetch(API+'/api/cascada',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selecciones)});
        const d=await r.json();
        selecciones.cuenca=selecciones.cuenca.filter(c=>d.cuencas.includes(c));
        selecciones.provincia=selecciones.provincia.filter(p=>d.provincias.includes(p));
        selecciones.distrito=selecciones.distrito.filter(x=>d.distritos.includes(x));
        llenarChecklist('filtro-cuenca',d.cuencas,selecciones.cuenca);
        llenarChecklist('filtro-provincia',d.provincias,selecciones.provincia);
        llenarChecklist('filtro-distrito',d.distritos,selecciones.distrito);
    }catch(e){console.error('Cascada:',e);}
}

// ── FILTRO SUBCUENCAS — dropdown dinámico según cuencas seleccionadas ─────────
async function actualizarFiltrosSubcuenca(cuencasSeleccionadas) {
    const contenedorSub = document.getElementById('contenedor-filtro-subcuenca');
    if (!contenedorSub) return;
    
    if (!cuencasSeleccionadas || cuencasSeleccionadas.length === 0) {
        contenedorSub.style.display = 'none';
        selecciones.subcuenca = [];
        llenarChecklist('filtro-subcuenca', [], []);
        setAnchor('filtro-subcuenca', []);
        return;
    }
    
    try {
        const paramCuencas = encodeURIComponent(cuencasSeleccionadas.join(','));
        const r = await fetch(API + `/api/poligonos/subcuencas?cuencas=${paramCuencas}&solo_nombres=1`);
        const d = await r.json();
        const nombres = (d.nombres || []).sort();
        
        if (nombres.length === 0) {
            contenedorSub.style.display = 'none';
            selecciones.subcuenca = [];
            return;
        }
        
        // Mantener selecciones vigentes
        selecciones.subcuenca = selecciones.subcuenca.filter(s => nombres.includes(s));
        llenarChecklist('filtro-subcuenca', nombres, selecciones.subcuenca);
        setAnchor('filtro-subcuenca', selecciones.subcuenca);
        contenedorSub.style.display = 'block';
    } catch(e) {
        console.warn('Error cargando subcuencas:', e);
    }
}
fetch(API+'/api/filtros?t='+Date.now()).then(r=>r.json()).then(d=>{
    llenarChecklist('filtro-tipo',d.tipos,[]);
    llenarChecklist('filtro-cuenca',d.cuencas,[]);
    llenarChecklist('filtro-provincia',d.provincias,[]);
    llenarChecklist('filtro-distrito',d.distritos,[]);
    aplicarFiltros();
});

// ── 6. SIMBOLOGÍA ─────────────────────────────────────────────────────────────
const mapeoEntidades = {
    "DERECHOS DE USO DE AGUA":          {logo:"logo_ana.png",     nombreCompleto:"Autoridad Nacional del Agua"},
    "FUENTES CONTAMINANTES":            {logo:"logo_ana.png",     nombreCompleto:"Autoridad Nacional del Agua"},
    "PUNTOS DE MUESTREO ANA":           {logo:"logo_ana.png",     nombreCompleto:"Autoridad Nacional del Agua"},
    "RED DE MONITOREO ANA":             {logo:"logo_ana.png",     nombreCompleto:"Autoridad Nacional del Agua"},
    "CENTROS POBLADOS CON MP":          {logo:"logo_diresa.png",  nombreCompleto:"Dirección Regional de Salud Áncash"},
    "GRAN Y MEDIANA MINERÍA":           {logo:"logo_drem.png",    nombreCompleto:"Dirección Regional de Energía y Minas"},
    "PEQUEÑA MINERÍA":                  {logo:"logo_drem.png",    nombreCompleto:"Dirección Regional de Energía y Minas"},
    "REINFOS":                          {logo:"logo_drem.png",    nombreCompleto:"Dirección Regional de Energía y Minas"},
    "SITIOS CONTAMINADOS CON DAR":      {logo:"logo_inaigem.png", nombreCompleto:"Instituto Nacional de Glaciología"},
    "PUNTOS DE CONTAMINACIÓN AMBIENTAL":{logo:"logo_ipfca.png",   nombreCompleto:"IPFCA"},
    "PASIVOS AMBIENTALES MINEROS":      {logo:"logo_minem.png",   nombreCompleto:"Ministerio de Energía y Minas"},
    "ADRS MUNICIPALES":                 {logo:"logo_oefa.png",    nombreCompleto:"Organismo de Evaluación y Fiscalización Ambiental"},
    "ADRS NO MUNICIPALES":              {logo:"logo_oefa.png",    nombreCompleto:"Organismo de Evaluación y Fiscalización Ambiental"},
    "INFRAESTRUCTURA DE RRSS":          {logo:"logo_oefa.png",    nombreCompleto:"Organismo de Evaluación y Fiscalización Ambiental"},
    "PUNTOS DE MUESTREO OEFA":          {logo:"logo_oefa.png",    nombreCompleto:"Organismo de Evaluación y Fiscalización Ambiental"},
    "UNIDADES FISCALIZABLES OEFA":      {logo:"logo_oefa.png",    nombreCompleto:"Organismo de Evaluación y Fiscalización Ambiental"},
    "PUNTOS DE MUESTREO SENASA":        {logo:"logo_senasa.png",  nombreCompleto:"Servicio Nacional de Sanidad Agraria"},
    "DOSAJES METALES CP":              {logo:"logo_diresa.png",    nombreCompleto:"Dirección Regional de Salud Áncash"},
    "PUNTOS CRÍTICOS":                 {logo:"logo_ana.png",       nombreCompleto:"Autoridad Nacional del Agua"},
    "ACREDITACIÓN DE DISPONIBILIDAD HÍDRICA":{logo:"logo_ana.png",  nombreCompleto:"Autoridad Nacional del Agua"},
    "FORMALIZACIÓN DE DERECHOS DE USO":{logo:"logo_ana.png",       nombreCompleto:"Autoridad Nacional del Agua"},
};

const configSimbologia = {
    "DERECHOS DE USO DE AGUA":          {icono:"fa-hand-holding-droplet", color:"#00a8ff"},
    "FUENTES CONTAMINANTES":            {icono:"fa-industry",             color:"#8e44ad"},
    "PUNTOS DE MUESTREO ANA":           {icono:"fa-flask",                color:"#2980b9"},
    "RED DE MONITOREO ANA":             {icono:"fa-flask",                color:"#1a6fa3"},
    "CENTROS POBLADOS CON MP":          {icono:"fa-house-medical",        color:"#e74c3c"},
    "GRAN Y MEDIANA MINERÍA":           {icono:"fa-helmet-safety",        color:"#7f6000"},
    "PEQUEÑA MINERÍA":                  {icono:"fa-helmet-safety",        color:"#b8860b"},
    "REINFOS":                          {icono:"fa-database",             color:"#6c757d"},
    "SITIOS CONTAMINADOS CON DAR":      {icono:"fa-droplet",              color:"#d62728"},
    "PUNTOS DE CONTAMINACIÓN AMBIENTAL":{icono:"fa-triangle-exclamation", color:"#e67e22"},
    "PASIVOS AMBIENTALES MINEROS":      {icono:"fa-radiation",            color:"#8B4513"},
    "ADRS MUNICIPALES":                 {icono:"fa-dumpster",             color:"#c0392b"},
    "ADRS NO MUNICIPALES":              {icono:"fa-dumpster",             color:"#922b21"},
    "INFRAESTRUCTURA DE RRSS":          {icono:"fa-recycle",              color:"#27ae60"},
    "PUNTOS DE MUESTREO OEFA":          {icono:"fa-flask",                color:"#8e44ad"},
    "UNIDADES FISCALIZABLES OEFA":      {icono:"fa-building",             color:"#d35400"},
    "PUNTOS DE MUESTREO SENASA":        {icono:"fa-seedling",             color:"#229954"},
    "DOSAJES METALES CP":               {icono:"fa-vial-virus",           color:"#c0392b"},
    "PUNTOS CRÍTICOS":                  {icono:"fa-house-flood-water",    color:"#0e7490"},
    "ACREDITACIÓN DE DISPONIBILIDAD HÍDRICA":{icono:"fa-file-circle-check", color:"#0891b2"},
    "FORMALIZACIÓN DE DERECHOS DE USO": {icono:"fa-stamp",                color:"#0369a1"},
};

// ── 7. DETALLE DE PUNTO — carga CSV del dataset ───────────────────────────────
async function abrirPanelDetalles(punto) {
    document.getElementById('panel-info-iniciativa').style.display='none';
    const pd = document.getElementById('panel-detalles');
    pd.style.display = 'flex';

    const tipoKey = String(punto.Tipo_Dataset||'').toUpperCase().trim();
    const ie  = mapeoEntidades[tipoKey] || {};
    const sim = configSimbologia[tipoKey] || {};
    const color = sim.color || '#0182c7';

    // ── Top bar: icono coloreado + tipo + cerrar ──
    const topBar = document.getElementById('det-top-bar');
    if(topBar) topBar.style.borderBottom = `3px solid ${color}`;
    const topIcono = document.getElementById('det-top-icono');
    if(topIcono) topIcono.innerHTML = `<i class="fa-solid ${sim.icono||'fa-location-dot'}" style="color:${color};"></i>`;
    const topTipo = document.getElementById('det-top-tipo');
    if(topTipo) topTipo.textContent = punto.Tipo_Dataset || '—';

    // ── Banda entidad ──
    const entBar = document.getElementById('det-entidad-bar');
    if(entBar) entBar.style.background = `linear-gradient(135deg, ${color}18 0%, ${color}08 100%)`;
    const entNombre = document.getElementById('det-entidad-nombre');
    if(entNombre) entNombre.textContent = ie.nombreCompleto || '—';
    const entLogo = document.getElementById('det-entidad-logo');
    if(entLogo){
        if(ie.logo){ entLogo.src=ie.logo; entLogo.style.display='block'; }
        else entLogo.style.display='none';
    }

    // ── Tarjetas de ubicación ──
    const campos = [
        {c:'Cuenca',    i:'fa-water',            cl:'#2980b9', l:'Cuenca'},
        {c:'Provincia', i:'fa-map-location-dot', cl:'#27ae60', l:'Provincia'},
        {c:'Distrito',  i:'fa-map-pin',          cl:'#e74c3c', l:'Distrito'},
    ];
    let tarjetas = '';
    campos.forEach(({c,i,cl,l})=>{
        if(punto[c]&&String(punto[c]).trim())
            tarjetas += `<div class="det-card" style="border-left-color:${cl};">
                <div class="det-card-label"><i class="fa-solid ${i}" style="color:${cl};"></i> ${l}</div>
                <div class="det-card-val">${punto[c]}</div>
            </div>`;
    });

    // ── Campos adicionales del índice ──
    const excl=['Tipo_Dataset','Entidad','Cuenca','Provincia','Distrito','X','Y',
                'Latitud','Longitud','Zona_UTM','tipo_coords','Departamento',
                'archivo_detalle','ID_registro'];
    let extrasHTML='';
    for(let col in punto){
        const val=punto[col];
        if(!excl.includes(col)&&val!==undefined&&val!==null&&String(val).trim()!=='')
            extrasHTML+=`<div class="det-field">
                <span class="det-field-key">${col}</span>
                <span class="det-field-val">${String(val)}</span>
            </div>`;
    }

    const archivo = punto.archivo_detalle||'';
    const idReg   = punto.ID_registro||'';

    let html = `
        <div class="det-cards-grid">${tarjetas}</div>
        ${extrasHTML ? `<div class="det-extra-section">${extrasHTML}</div>` : ''}
        ${archivo ? `
        <div class="det-dataset-box" id="detalle-dataset">
            <div class="det-dataset-header">
                <i class="fa-solid fa-database"></i>
                <span>Cargando <strong>${archivo}</strong>...</span>
            </div>
        </div>` : ''}`;

    document.getElementById('contenido-detalles').innerHTML = html;

    // ── Carga del dataset ──
    if(archivo){
        try{
            const r = await fetch(API+'/api/detalle-punto',{
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({archivo_detalle:archivo, id_registro:idReg})
            });
            const d = await r.json();
            const box = document.getElementById('detalle-dataset');
            if(!box) return;

            if(d.ok && d.campos && Object.keys(d.campos).length > 0){
                const excl2=['ID','Id','id','ID_registro','X','Y','Lat','Long'];
                let camposHTML='';
                for(let col in d.campos){
                    const val=d.campos[col];
                    if(!excl2.includes(col)&&val&&String(val).trim())
                        camposHTML+=`<div class="det-field">
                            <span class="det-field-key">${col}</span>
                            <span class="det-field-val">${val}</span>
                        </div>`;
                }
                box.innerHTML=`<div class="det-dataset-header" style="color:${color};">
                    <i class="fa-solid fa-database"></i>
                    <span>${archivo.replace('.csv','')}</span>
                </div>
                <div class="det-dataset-fields">${camposHTML||'<p class="det-empty">Sin campos adicionales.</p>'}</div>`;
            } else {
                box.innerHTML=`<div class="det-dataset-header">
                    <i class="fa-solid fa-database"></i><span>${archivo.replace('.csv','')}</span>
                </div>
                <p class="det-error"><i class="fa-solid fa-triangle-exclamation"></i> ${d.error||'Sin datos detallados.'}</p>
                ${d.columnas?.length?`<p class="det-cols">Columnas: ${d.columnas.join(', ')}</p>`:''}`;
            }
        }catch(e){
            const box=document.getElementById('detalle-dataset');
            if(box) box.innerHTML=`<p class="det-error">Error: ${e.message}</p>`;
        }
    }
}

// ── 8. APLICAR FILTROS ────────────────────────────────────────────────────────
let datosGlobalesCSV=[];
let geomSubcuencasActivas = null; // GeoJSON features de las subcuencas seleccionadas

// ── Point-in-polygon (ray casting, sin dependencias) ──────────────────────────
function puntoDentroDeFeature(lat, lng, feature) {
    const geom = feature.geometry;
    const pt = [lng, lat];
    if (geom.type === 'Polygon')     return _rayPoligono(pt, geom.coordinates);
    if (geom.type === 'MultiPolygon') return geom.coordinates.some(p => _rayPoligono(pt, p));
    return false;
}
function _rayPoligono(pt, rings) {
    // rings[0] = exterior, rings[1..] = huecos
    return _rayRing(pt, rings[0]) && !rings.slice(1).some(r => _rayRing(pt, r));
}
function _rayRing(pt, ring) {
    let inside = false;
    const [x, y] = pt;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi)
            inside = !inside;
    }
    return inside;
}
function puntoEnSubcuencasSeleccionadas(lat, lng) {
    if (!geomSubcuencasActivas || geomSubcuencasActivas.length === 0) return true;
    return geomSubcuencasActivas.some(f => puntoDentroDeFeature(lat, lng, f));
}

// --- MANEJO DE FILTROS SECUNDARIOS DINÁMICOS ---
async function actualizarFiltrosSecundarios(tiposSeleccionados) {
    const contenedor = document.getElementById('contenedor-filtros-secundarios');
    if (!tiposSeleccionados || tiposSeleccionados.length === 0) {
        contenedor.style.display = 'none'; contenedor.innerHTML = '';
        selecciones.secundarios = {}; return;
    }

    try {
        const r = await fetch(API + '/api/filtros-secundarios', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(tiposSeleccionados)
        });
        const filtrosDisp = await r.json();

        if (Object.keys(filtrosDisp).length === 0) {
            contenedor.style.display = 'none'; contenedor.innerHTML = '';
            selecciones.secundarios = {}; return;
        }

        contenedor.style.display = 'block';
        let html = '<p style="margin:0 0 8px 0; font-size:11px; font-weight:bold; color:#0182c7; text-transform:uppercase;"><i class="fa-solid fa-filter" style="margin-right:5px;"></i>Filtros Específicos</p>';
        
        // Limpieza de estados si se desmarcó una categoría
        for (let k in selecciones.secundarios) { if (!filtrosDisp[k]) delete selecciones.secundarios[k]; }

        for (let columna in filtrosDisp) {
            if (!selecciones.secundarios[columna]) selecciones.secundarios[columna] = [];
            
            html += `
            <div style="margin-bottom: 10px;">
                <label class="titulo-filtro" style="margin: 0 0 4px 0; font-size: 10px; font-weight:600; color:#333;">Por ${columna}:</label>
                <div class="dropdown-check-list" id="dd-sec-${columna}">
                    <span class="anchor" style="padding: 6px; font-size: 11px; background:#fff;">Seleccione...</span>
                    <ul class="items" id="filtro-sec-${columna}">`;
            
            filtrosDisp[columna].forEach(val => {
                const checked = selecciones.secundarios[columna].includes(val) ? 'checked' : '';
                html += `<li><label style="font-size: 11px; text-transform: none; font-weight:normal; color:#444;"><input type="checkbox" value="${val}" ${checked} data-columna="${columna}"> ${val}</label></li>`;
            });
            html += `</ul></div></div>`;
        }
        
        contenedor.innerHTML = html;

        // Reactivar el comportamiento de dropdown nativo del visor
        contenedor.querySelectorAll('.dropdown-check-list .anchor').forEach(a => {
            a.onclick = function(e) {
                e.stopPropagation();
                document.querySelectorAll('.dropdown-check-list').forEach(dd => {
                    if (dd !== this.parentElement) dd.classList.remove('visible');
                });
                this.parentElement.classList.toggle('visible');
            };
        });

        // Eventos de selección para checkboxes dinámicos
        contenedor.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const col = e.target.getAttribute('data-columna');
                const marcados = Array.from(contenedor.querySelectorAll(`input[data-columna="${col}"]:checked`)).map(c => c.value);
                selecciones.secundarios[col] = marcados;
                
                const anchor = document.getElementById(`dd-sec-${col}`).querySelector('.anchor');
                anchor.innerText = marcados.length === 0 ? 'Seleccione...' : (marcados.length === 1 ? marcados[0] : `${marcados.length} seleccionados`);
                aplicarFiltros();
            });
            
            // Setear texto inicial al recargar
            const col = cb.getAttribute('data-columna');
            if (selecciones.secundarios[col] && selecciones.secundarios[col].length > 0) {
                const anchor = document.getElementById(`dd-sec-${col}`).querySelector('.anchor');
                anchor.innerText = selecciones.secundarios[col].length === 1 ? selecciones.secundarios[col][0] : `${selecciones.secundarios[col].length} seleccionados`;
            }
        });
    } catch (e) { console.error('Error cargando filtros secundarios:', e); }
}

// ── Dibujo de polígonos seleccionados ─────────────────────────────────────────
// Pide al backend únicamente las geometrías seleccionadas (ya recortadas a
// Áncash) en lugar de descargar el archivo completo y filtrarlo en el navegador.
const PROPS_NOMBRE = {
    distritos : ['DISTRITO','NOM_DIST','NOMBDIST'],
    provincias: ['PROVINCIA','NOM_PROV','NOMBPROV'],
    cuencas   : ['NOMBRE','CUENCA','Nombre']
};

function normaliza(txt){
    return String(txt||'').normalize('NFD').replace(/[̀-ͯ]/g,'')
        .replace(/\s+/g,' ').trim().toUpperCase();
}

function dibujarPoligonos(recurso, seleccion, capa, opciones){
    if(!seleccion || !seleccion.length) return;
    const param = encodeURIComponent(seleccion.join(','));
    const props = PROPS_NOMBRE[recurso] || [];
    const buscados = seleccion.map(normaliza);

    fetch(`${API}/api/poligonos/${recurso}?nombres=${param}`)
        .then(r=>r.json())
        .then(geo=>{
            // Red de seguridad: si el backend fuese una versión antigua sin
            // soporte de ?nombres=, se filtra igualmente en el cliente.
            const total = (geo.features||[]).length;
            const necesitaFiltro = total > seleccion.length * 3;
            L.geoJSON(geo, {
                pane: opciones.pane,
                interactive: false,
                filter: f => {
                    if(!necesitaFiltro) return true;
                    const p = f.properties || {};
                    const dep = p.DEPARTAMEN || p.DEPARTAMENTO || p.NOMBDEP || p.NOM_DEP || p.DPTO || '';
                    if(dep && normaliza(dep) !== 'ANCASH') return false;
                    for(const clave of props){
                        const v = p[clave];
                        if(!v) continue;
                        const partes = normaliza(v).split('/').map(s=>s.trim());
                        if(partes.some(x=>buscados.includes(x)) || buscados.includes(normaliza(v)))
                            return true;
                    }
                    return false;
                },
                style: { color: opciones.color, weight: 2, fillOpacity: parseFloat(opciones.fillOpacity) }
            }).addTo(capa);
        })
        .catch(e=>console.warn(`Polígonos ${recurso}:`, e));
}

function aplicarFiltros(){
    const txtRes=document.getElementById('contador-resultados');
    if(!selecciones.tipo.length&&!selecciones.cuenca.length&&!selecciones.provincia.length&&!selecciones.distrito.length){
        capaCuencas.clearLayers();capaProvincias.clearLayers();capaDistritos.clearLayers();capaSubcuencas.clearLayers();
        capaPuntosCluster.clearLayers();capaPuntosIndividual.clearLayers();
        if(txtRes) txtRes.innerHTML='Resultados: 0 puntos (Seleccione al menos un filtro).';
        document.getElementById('btn-descargar-csv').style.display='none';
        document.getElementById('leyenda-mapa').style.display='none';
        datosGlobalesCSV=[]; return;
    }
    if(txtRes) txtRes.innerHTML='Resultados: Buscando...';
    fetch(API+'/api/filtrar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selecciones)})
        .then(r=>r.json()).then(datos=>{
            capaCuencas.clearLayers();capaProvincias.clearLayers();capaDistritos.clearLayers();capaSubcuencas.clearLayers();
            capaPuntosCluster.clearLayers();capaPuntosIndividual.clearLayers();
            if(txtRes) txtRes.innerHTML=`Resultados: <strong>${datos.cantidad_total}</strong> puntos encontrados.`;
            datosGlobalesCSV=datos.puntos;
            document.getElementById('btn-descargar-csv').style.display=datos.cantidad_total>0?'flex':'none';

            // Leyenda
            let leg=''; const tipos=new Set();
            datos.puntos.forEach(p=>{if(p.Tipo_Dataset) tipos.add(String(p.Tipo_Dataset).toUpperCase().trim());});
            tipos.forEach(t=>{
                for(let k in configSimbologia){
                    if(String(k).toUpperCase().trim()===t){
                        leg+=`<div class="leyenda-item"><i class="fa-solid ${configSimbologia[k].icono}" style="color:${configSimbologia[k].color};font-size:13px;margin-right:6px;"></i>${k}</div>`;break;
                    }
                }
            });

            const opC=document.getElementById('slider-cuenca')?.value||0.15;
            const opP=document.getElementById('slider-provincia')?.value||0.15;
            const opD=document.getElementById('slider-distrito')?.value||0.25;
            const opS=document.getElementById('slider-subcuenca')?.value||0.20;

            // ── Polígonos: se piden al backend SOLO los seleccionados y ya
            //    recortados al departamento de Áncash (parámetro ?nombres=) ──
            if(selecciones.distrito.length){
                leg+=`<div class="leyenda-item"><div class="leyenda-poly" style="background:#2ca02c;border-color:#2ca02c;"></div>Distritos</div>`;
                dibujarPoligonos('distritos', selecciones.distrito, capaDistritos,
                    {pane:'paneDistritos', color:"#2ca02c", fillOpacity:opD});
            }
            if(selecciones.provincia.length){
                leg+=`<div class="leyenda-item"><div class="leyenda-poly" style="background:#ff7f0e;border-color:#ff7f0e;"></div>Provincias</div>`;
                dibujarPoligonos('provincias', selecciones.provincia, capaProvincias,
                    {pane:'paneProvincias', color:"#ff7f0e", fillOpacity:opP});
            }
            if(selecciones.cuenca.length){
                leg+=`<div class="leyenda-item"><div class="leyenda-poly" style="background:#0068c9;border-color:#0068c9;"></div>Cuencas</div>`;
                dibujarPoligonos('cuencas', selecciones.cuenca, capaCuencas,
                    {pane:'paneCuencas', color:"#0068c9", fillOpacity:opC});
            } else {
                capaSubcuencas.clearLayers();
            }
            // Subcuencas: solo si hay selección explícita en el filtro
            if(selecciones.subcuenca.length){
                leg+=`<div class="leyenda-item"><div class="leyenda-poly" style="background:#00b4d8;border-color:#0096c7;"></div>Subcuencas</div>`;
                const paramSub=encodeURIComponent(selecciones.subcuenca.join(','));
                fetch(API+`/api/poligonos/subcuencas?nombres=${paramSub}`).then(r=>r.json()).then(geo=>{
                    capaSubcuencas.clearLayers();
                    // Guardar features para filtrado punto-en-polígono
                    geomSubcuencasActivas = geo.features || [];
                    L.geoJSON(geo,{
                        pane:'paneSubcuencas', interactive:true,
                        style:{color:"#0096c7",weight:1.5,fillColor:"#00b4d8",fillOpacity:parseFloat(opS)},
                        onEachFeature:(f,layer)=>{
                            const nombre=f.properties.Nombre_UH||'Subcuenca';
                            const area=parseFloat(f.properties.AREA_KM2||f.properties.Area||0);
                            const codigo=f.properties.CODIGO||'';
                            layer.on('click', e=>{
                                L.DomEvent.stopPropagation(e);
                                mapa.closePopup();
                                const html=`<div class="popup-subcuenca">
                                    <div class="popup-sub-header">
                                        <i class="fa-solid fa-water"></i>
                                        <span>${nombre}</span>
                                    </div>
                                    <div class="popup-sub-body">
                                        ${area>0?`<div class="popup-sub-row"><span class="popup-sub-label">Área</span><span class="popup-sub-val">${area.toFixed(1)} km²</span></div>`:''}
                                        ${codigo?`<div class="popup-sub-row"><span class="popup-sub-label">Código</span><span class="popup-sub-val">${codigo}</span></div>`:''}
                                    </div>
                                </div>`;
                                L.popup({className:'popup-sub-custom', closeButton:true, maxWidth:240, offset:[0,-4]})
                                    .setLatLng(e.latlng).setContent(html).openOn(mapa);
                            });
                            layer.on('mouseover', ()=>layer.setStyle({fillOpacity:Math.min(parseFloat(opS)+0.2,0.85),weight:2.5}));
                            layer.on('mouseout',  ()=>layer.setStyle({fillOpacity:parseFloat(opS),weight:1.5}));
                        }
                    }).addTo(capaSubcuencas);
                    // Re-filtrar marcadores con geometría disponible
                    renderizarMarcadosFiltrados(datosGlobalesCSV, document.getElementById('toggle-cluster')?.checked??true);
                }).catch(e=>console.warn('Subcuencas:',e));
            } else {
                capaSubcuencas.clearLayers();
                geomSubcuencasActivas = null;
            }
            if(leg){document.getElementById('leyenda-contenido').innerHTML=leg;document.getElementById('leyenda-mapa').style.display='block';}

            // Si no hay subcuencas activas aún, renderizar inmediatamente
            // Si hay, se renderizará cuando llegue el GeoJSON de subcuencas
            if(!selecciones.subcuenca.length){
                geomSubcuencasActivas = null;
                renderizarMarcadosFiltrados(datos.puntos, document.getElementById('toggle-cluster')?.checked??true);
            }
            cargarCategorias();
        });
}
function renderizarMarcadosFiltrados(puntos, useCluster) {
    capaPuntosCluster.clearLayers();
    capaPuntosIndividual.clearLayers();
    let marcadores=[];
    let contadorFiltrado = 0;
    puntos.forEach(punto=>{
        if(!punto.Latitud||!punto.Longitud||punto.Latitud===""||punto.Longitud==="") return;
        const lat=parseFloat(punto.Latitud), lng=parseFloat(punto.Longitud);
        if(isNaN(lat)||isNaN(lng)) return;
        // Filtro por subcuenca (point-in-polygon)
        if(!puntoEnSubcuencasSeleccionadas(lat, lng)) return;
        contadorFiltrado++;
        const conf=configSimbologia[String(punto.Tipo_Dataset||'').toUpperCase().trim()];
        const m=conf
            ?L.marker([lat,lng],{icon:L.divIcon({html:`<i class="fa-solid ${conf.icono}" style="color:${conf.color};font-size:16px;"></i>`,className:'',iconSize:[16,16],iconAnchor:[8,16]}),pane:'panePuntos'})
            :L.circleMarker([lat,lng],{pane:'panePuntos',radius:5,color:"#333",fillOpacity:0.8});
        m.on('click',()=>abrirPanelDetalles(punto));
        marcadores.push(m);
    });
    if(useCluster){mapa.addLayer(capaPuntosCluster);mapa.removeLayer(capaPuntosIndividual);capaPuntosCluster.addLayers(marcadores);}
    else{mapa.addLayer(capaPuntosIndividual);mapa.removeLayer(capaPuntosCluster);marcadores.forEach(m=>m.addTo(capaPuntosIndividual));}
    // Actualizar contador si hubo filtro por subcuenca
    if(geomSubcuencasActivas && geomSubcuencasActivas.length>0){
        const txtRes=document.getElementById('contador-resultados');
        if(txtRes) txtRes.innerHTML=`Resultados: <strong>${contadorFiltrado}</strong> puntos en subcuenca(s) seleccionada(s).`;
    }
}

document.getElementById('toggle-cluster')?.addEventListener('change',aplicarFiltros);
document.getElementById('slider-cuenca')?.addEventListener('input',e=>capaCuencas.eachLayer(l=>{if(l.setStyle)l.setStyle({fillOpacity:e.target.value});}));
document.getElementById('slider-provincia')?.addEventListener('input',e=>capaProvincias.eachLayer(l=>{if(l.setStyle)l.setStyle({fillOpacity:e.target.value});}));
document.getElementById('slider-distrito')?.addEventListener('input',e=>capaDistritos.eachLayer(l=>{if(l.setStyle)l.setStyle({fillOpacity:e.target.value});}));
document.getElementById('slider-subcuenca')?.addEventListener('input',e=>capaSubcuencas.eachLayer(l=>{if(l.setStyle)l.setStyle({fillOpacity:e.target.value});}));
document.getElementById('btn-descargar-csv')?.addEventListener('click',()=>{
    if(!datosGlobalesCSV.length) return;
    let cols=new Set(); datosGlobalesCSV.forEach(f=>{for(let c in f)if(f[c]!=="")cols.add(c);});
    const h=Array.from(cols); let csv="\uFEFF"+h.join(",")+"\n";
    datosGlobalesCSV.forEach(r=>{csv+=h.map(k=>`"${(r[k]==null?"":String(r[k])).replace(/"/g,'""')}"`).join(",")+"\n";});
    const a=document.createElement("a"); a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'})); a.download="SICAR_Ancash.csv"; a.click();
});

// ── 9. CHATBOT ────────────────────────────────────────────────────────────────
let pregDisponibles={};
fetch(API+'/api/chat/preguntas').then(r=>r.json()).then(d=>{pregDisponibles=d;cargarCategorias();setTimeout(initChat,100);}).catch(()=>{});

function initChat(){
    const h=document.getElementById('chatbot-header'),b=document.getElementById('chatbot-body'),bt=document.getElementById('btn-toggle-chat');
    if(h&&b&&bt){h.style.cursor='pointer';h.addEventListener('click',()=>{const v=b.style.display==='flex';b.style.display=v?'none':'flex';bt.innerText=v?'▲':'▼';});}
    document.getElementById('btn-enviar-chat')?.addEventListener('click',enviarChat);
    document.getElementById('chat-input')?.addEventListener('keypress',e=>{if(e.key==='Enter')enviarChat();});
    document.getElementById('btn-reset-chat')?.addEventListener('click',e=>{
        e.stopPropagation();
        selecciones={tipo:[],cuenca:[],subcuenca:[],provincia:[],distrito:[],secundarios:{}};
        document.querySelectorAll('input[type="checkbox"]').forEach(cb=>cb.checked=false);
        document.querySelectorAll('.anchor').forEach(a=>a.innerText='Seleccione opciones...');
        const md=document.getElementById('chat-mensajes');
        if(md) md.innerHTML='<div class="msj-bot">¡Hola! Selecciona una categoría.</div>';
        const pd=document.getElementById('chat-preguntas');
        if(pd){pd.innerHTML='';pd.style.display='none';}
        cargarCategorias(); aplicarFiltros();
    });
}
function cargarCategorias(){
    const div=document.getElementById('chat-categorias'); if(!div)return;
    let p=new URLSearchParams();
    if(selecciones.tipo.length)     p.append('tipo',    selecciones.tipo.join(", "));
    if(selecciones.cuenca.length)   p.append('cuenca',  selecciones.cuenca.join(", "));
    if(selecciones.provincia.length)p.append('provincia',selecciones.provincia.join(", "));
    if(selecciones.distrito.length) p.append('distrito', selecciones.distrito.join(", "));
    fetch(API+'/api/chat/preguntas?'+p).then(r=>r.json()).then(d=>{
        pregDisponibles=d; div.innerHTML='';
        for(let cat in d){
            const btn=document.createElement('button'); btn.textContent=cat;
            btn.style.cssText='padding:7px 11px;margin:3px;background:#0182c7;color:white;border:none;border-radius:20px;cursor:pointer;font-size:12px;';
            btn.onmouseover=()=>btn.style.background='#0068c9'; btn.onmouseout=()=>btn.style.background='#0182c7';
            btn.onclick=()=>cargarPreguntas(cat); div.appendChild(btn);
        }
    }).catch(()=>{});
}
function cargarPreguntas(cat){
    const div=document.getElementById('chat-preguntas'); if(!div)return;
    div.innerHTML=''; div.style.display='block';
    (pregDisponibles[cat]||[]).forEach(([preg])=>{
        const btn=document.createElement('button'); btn.textContent=preg;
        btn.style.cssText='display:block;width:calc(100% - 20px);padding:7px;margin:4px 10px;background:#f0f0f0;border:1px solid #ddd;border-radius:5px;cursor:pointer;font-size:12px;text-align:left;';
        btn.onmouseover=()=>btn.style.background='#e0e0e0'; btn.onmouseout=()=>btn.style.background='#f0f0f0';
        btn.onclick=()=>enviarConsulta(preg); div.appendChild(btn);
    });
}
function enviarConsulta(txt){
    const md=document.getElementById('chat-mensajes');
    md.innerHTML+=`<div class="msj-user">${txt}</div>`; md.scrollTop=md.scrollHeight;
    const id="c"+Date.now(); md.innerHTML+=`<div class="msj-bot" id="${id}">Buscando...</div>`;
    const pf=`${txt}|||${selecciones.tipo.join(",")}|||${selecciones.cuenca.join(",")}|||${selecciones.provincia.join(",")}|||${selecciones.distrito.join(",")}`;
    fetch(API+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pregunta:pf})})
        .then(r=>r.json()).then(d=>{document.getElementById(id).innerHTML=d.respuesta;md.scrollTop=md.scrollHeight;})
        .catch(()=>{document.getElementById(id).innerHTML="Error.";});
}
async function enviarChat(){
    const inp=document.getElementById('chat-input'),txt=inp.value.trim(); if(!txt)return;
    inp.value=''; enviarConsulta(txt);
}

// ── 10. INICIATIVAS ───────────────────────────────────────────────────────────
let todasIniciativas=[],marcadoresIni=[],selIdx=null;
let gjCuencas=null,fotosIni=[],idxFoto=0,iniciativasCargadas=false;
const COLORES=['#27ae60','#2ecc71','#16a085','#1abc9c','#2980b9','#3498db','#8e44ad','#9b59b6','#d35400','#e67e22','#c0392b'];

function radPlantones(p){const n=Number(p)||0;if(n<=0)return 7;if(n<1000)return 9;if(n<10000)return 12;if(n<100000)return 16;if(n<500000)return 20;return 25;}

// Hacer arrastrables ambos paneles
const panelIni=document.getElementById('panel-iniciativas');
const panelIniHdr=document.getElementById('panel-iniciativas-header');
if(panelIni&&panelIniHdr) hacerArrastrable(panelIni,panelIniHdr);

const panelInfoIni=document.getElementById('panel-info-iniciativa');
const panelInfoIniHdr=document.getElementById('panel-info-ini-header');
if(panelInfoIni&&panelInfoIniHdr) hacerArrastrable(panelInfoIni,panelInfoIniHdr);

// Abrir/cerrar/colapsar
document.getElementById('btn-abrir-iniciativas')?.addEventListener('click',()=>{
    panelIni.style.display='flex';
    document.getElementById('btn-abrir-iniciativas').style.display='none';
    if(!iniciativasCargadas){iniciativasCargadas=true;cargarIniciativas();}
});
document.getElementById('btn-cerrar-iniciativas')?.addEventListener('click',()=>{
    panelIni.style.display='none';
    document.getElementById('btn-abrir-iniciativas').style.display='flex';
});
let iniColap=false;
document.getElementById('btn-colapsar-iniciativas')?.addEventListener('click',()=>{
    iniColap=!iniColap;
    document.getElementById('panel-iniciativas-body').style.display=iniColap?'none':'block';
    document.getElementById('btn-colapsar-iniciativas').textContent=iniColap?'▼':'▲';
});
document.getElementById('btn-cerrar-info-iniciativa')?.addEventListener('click',()=>{
    document.getElementById('panel-info-iniciativa').style.display='none'; limpiarSelIni();
});
document.getElementById('buscar-iniciativa')?.addEventListener('input',e=>{
    const q=e.target.value.toLowerCase();
    document.querySelectorAll('.iniciativa-item').forEach(item=>{item.style.display=item.dataset.nombre.toLowerCase().includes(q)?'':'none';});
});
document.getElementById('btn-limpiar-iniciativas')?.addEventListener('click',limpiarSelIni);

function limpiarSelIni(){
    selIdx=null;
    marcadoresIni.forEach(({m})=>m.setStyle({fillOpacity:0.85,opacity:1,weight:2,color:'#fff'}));
    document.querySelectorAll('.iniciativa-item').forEach(i=>i.classList.remove('activo','opacado'));
    if(gjCuencas) gjCuencas.setStyle({color:"#7f8c8d",weight:2,fillOpacity:0.15,fillColor:"#bdc3c7"});
    document.getElementById('btn-limpiar-iniciativas').style.display='none';
}

async function cargarIniciativas(){
    const lista=document.getElementById('lista-iniciativas');
    try{
        const r=await fetch(API+'/api/iniciativas');
        if(!r.ok) throw new Error(`HTTP ${r.status}`);
        todasIniciativas=await r.json();
        if(!Array.isArray(todasIniciativas)||!todasIniciativas.length){
            lista.innerHTML='<p style="color:#aaa;font-size:12px;text-align:center;padding:15px;">Sin proyectos.<br>Verifica <code>data/proyectos.csv</code></p>';
            iniciativasCargadas=false; return;
        }
        renderListaIni(); dibujarCirculosIni(); cargarCuencasFondo();
    }catch(e){
        iniciativasCargadas=false;
        lista.innerHTML=`<p style="color:#e74c3c;font-size:12px;padding:10px;">⚠ Error: ${e.message}</p>`;
    }
}

function renderListaIni(){
    const c=document.getElementById('lista-iniciativas'); if(!c)return; c.innerHTML='';
    todasIniciativas.forEach((p,idx)=>{
        const color=COLORES[idx%COLORES.length];
        const item=document.createElement('div'); item.className='iniciativa-item';
        item.dataset.nombre=p.Proyecto||''; item.dataset.idx=idx;
        item.innerHTML=`
            <div class="iniciativa-burbuja" style="background:${color};border:2px solid ${color};">
                <i class="fa-solid fa-seedling" style="font-size:12px;"></i>
            </div>
            <div style="flex:1;min-width:0;">
                <div class="iniciativa-nombre">${p.Proyecto||'Sin nombre'}</div>
                <div class="iniciativa-meta">
                    ${p.Cuenca?`<i class="fa-solid fa-water" style="color:#2980b9;margin-right:2px;font-size:9px;"></i>${p.Cuenca}`:''}
                    ${Number(p.Plantones)>0?` · 🌱${Number(p.Plantones).toLocaleString()}`:''}
                    ${p.Estado?` · <em>${p.Estado}</em>`:''}
                </div>
            </div>`;
        item.addEventListener('click',()=>seleccionarIni(idx));
        c.appendChild(item);
    });
}

function dibujarCirculosIni(){
    capaIniciativas.clearLayers(); marcadoresIni=[];
    todasIniciativas.forEach((p,idx)=>{
        const lat=Number(p.Lat),lng=Number(p.Long); if(isNaN(lat)||isNaN(lng)) return;
        const color=COLORES[idx%COLORES.length];
        const m=L.circleMarker([lat,lng],{pane:'paneIniciativas',radius:radPlantones(p.Plantones),fillColor:color,color:'#fff',weight:2,fillOpacity:0.85}).addTo(capaIniciativas);
        m.bindTooltip(`<b>${p.Proyecto||'Proyecto'}</b>${p.Lugar?`<br>📍 ${p.Lugar}`:''}${Number(p.Plantones)>0?`<br>🌱 ${Number(p.Plantones).toLocaleString()} plantones`:''}`,{sticky:true,direction:'top'});
        m.on('click',()=>seleccionarIni(idx));
        marcadoresIni.push({m,idx});
    });
}

function seleccionarIni(idx){
    const p=todasIniciativas[idx]; if(!p) return;
    selIdx=idx;
    marcadoresIni.forEach(({m},i)=>{
        if(i===idx) m.setStyle({fillOpacity:0.95,opacity:1,weight:3});
        else        m.setStyle({fillOpacity:0.15,opacity:0.3,weight:1});
    });
    document.querySelectorAll('.iniciativa-item').forEach((item,i)=>{
        if(i===idx){item.classList.add('activo');item.classList.remove('opacado');item.scrollIntoView({behavior:'smooth',block:'nearest'});}
        else{item.classList.remove('activo');item.classList.add('opacado');}
    });
    if(p.Cuenca) destacarCuenca(p.Cuenca);
    const lat=Number(p.Lat),lng=Number(p.Long);
    if(!isNaN(lat)&&!isNaN(lng)) mapa.flyTo([lat,lng],11,{duration:1.2});
    mostrarInfoIni(p);
    document.getElementById('btn-limpiar-iniciativas').style.display='block';
}

function mostrarInfoIni(p){
    document.getElementById('panel-detalles').style.display='none';
    document.getElementById('ini-titulo').innerText=p.Proyecto||'Proyecto';
    const plantones=Number(p.Plantones)||0;
    const area=p['Área']||p['Area']||p['Area (Ha)']||'—';
    fotosIni=[];
    const base=API+'/images/';
    ['Foto1','Foto2','Foto3','Foto4','Foto5'].forEach(k=>{if(p[k]&&p[k].trim()) fotosIni.push(base+p[k].trim());});

    let html=`<div class="ini-stats-grid">
        <div class="ini-stat-card"><div class="ini-stat-label"><i class="fa-solid fa-water" style="color:#2980b9;margin-right:3px;"></i>Cuenca</div><div class="ini-stat-value" style="font-size:11px;">${p.Cuenca||'—'}</div></div>
        <div class="ini-stat-card"><div class="ini-stat-label"><i class="fa-solid fa-map-location-dot" style="color:#e74c3c;margin-right:3px;"></i>Provincia</div><div class="ini-stat-value" style="font-size:11px;">${p.Provincia||'—'}</div></div>
        <div class="ini-stat-card" style="border-left-color:#e67e22;"><div class="ini-stat-label"><i class="fa-solid fa-ruler-combined" style="color:#e67e22;margin-right:3px;"></i>Área</div><div class="ini-stat-value">${area} ha</div></div>
        <div class="ini-stat-card" style="border-left-color:#27ae60;"><div class="ini-stat-label"><i class="fa-solid fa-seedling" style="color:#27ae60;margin-right:3px;"></i>Plantones</div><div class="ini-stat-value" style="color:#27ae60;">${plantones>0?plantones.toLocaleString():'—'}</div></div>
    </div>`;
    if(p.Lugar) html+=`<p style="font-size:12px;color:#666;margin:6px 0;"><i class="fa-solid fa-location-dot" style="color:#e74c3c;margin-right:4px;"></i><strong>Lugar:</strong> ${p.Lugar}</p>`;
    const excl=['Proyecto','Lat','Long','Cuenca','Provincia','Lugar','Área','Area','Area (Ha)','Plantones','Foto1','Foto2','Foto3','Foto4','Foto5'];
    let ext='';
    for(let col in p){ if(!excl.includes(col)&&p[col]&&String(p[col]).trim()) ext+=`<p style="margin:4px 0;font-size:11px;"><strong style="color:#0182c7;">${col}:</strong> ${p[col]}</p>`; }
    if(ext) html+=`<hr style="border:0;border-top:1px solid #eee;margin:8px 0;">${ext}`;
    html+=fotosIni.length>0
        ?`<button class="btn-galeria" id="btn-ver-fotos-ini"><i class="fa-solid fa-images"></i> Galería (${fotosIni.length} foto${fotosIni.length>1?'s':''})</button>`
        :`<p style="font-size:11px;color:#bbb;text-align:center;margin-top:8px;"><i class="fa-solid fa-image"></i> Sin fotografías</p>`;

    document.getElementById('contenido-info-iniciativa').innerHTML=html;
    document.getElementById('btn-ver-fotos-ini')?.addEventListener('click',()=>abrirGaleria());
    document.getElementById('panel-info-iniciativa').style.display='flex';
}

// Galería
function abrirGaleria(){idxFoto=0;verFoto();document.getElementById('modal-galeria-ini').classList.add('show');}
function verFoto(){
    document.getElementById('imagen-actual-ini').src=fotosIni[idxFoto];
    document.getElementById('contador-fotos-ini').innerText=`${idxFoto+1} / ${fotosIni.length}`;
    document.getElementById('galeria-titulo-ini').innerText=todasIniciativas[selIdx]?.Proyecto||'';
}
document.getElementById('btn-next-ini')?.addEventListener('click',()=>{idxFoto=(idxFoto+1)%fotosIni.length;verFoto();});
document.getElementById('btn-prev-ini')?.addEventListener('click',()=>{idxFoto=(idxFoto-1+fotosIni.length)%fotosIni.length;verFoto();});
document.getElementById('cerrar-galeria-ini')?.addEventListener('click',()=>document.getElementById('modal-galeria-ini').classList.remove('show'));
document.getElementById('modal-galeria-ini')?.addEventListener('click',e=>{if(e.target.id==='modal-galeria-ini') document.getElementById('modal-galeria-ini').classList.remove('show');});
document.addEventListener('keydown',e=>{
    if(e.key==='Escape') document.getElementById('modal-galeria-ini')?.classList.remove('show');
    if(document.getElementById('modal-galeria-ini')?.classList.contains('show')){
        if(e.key==='ArrowRight'){idxFoto=(idxFoto+1)%fotosIni.length;verFoto();}
        if(e.key==='ArrowLeft'){idxFoto=(idxFoto-1+fotosIni.length)%fotosIni.length;verFoto();}
    }
});

// Cuencas fondo
async function cargarCuencasFondo(){
    try{
        const r=await fetch(API+'/api/cuencas-sicar');
        const d=await r.json();
        gjCuencas=L.geoJSON(d,{pane:'paneCuencas',style:{color:"#7f8c8d",weight:2,fillOpacity:0.15,fillColor:"#bdc3c7"}}).addTo(mapa);
    }catch(e){console.warn('Cuencas:',e);}
}
function destacarCuenca(nombre){
    if(!gjCuencas) return;
    gjCuencas.setStyle({color:"#7f8c8d",weight:2,fillOpacity:0.15,fillColor:"#bdc3c7"});
    gjCuencas.eachLayer(l=>{
        const n=l.feature.properties?.nombre||l.feature.properties?.NOMBRE||l.feature.properties?.Cuenca||'';
        if(String(n).toUpperCase().trim()===String(nombre).toUpperCase().trim())
            l.setStyle({color:"#e74c3c",weight:3.5,fillOpacity:0.3,fillColor:"#e74c3c"});
    });
}