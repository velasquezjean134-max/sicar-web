"""
SICAR Áncash — Backend FastAPI
Arquitectura CSV:
  datos_index.csv  →  columnas: Tipo_Dataset, Cuenca, Provincia, Distrito, X, Y,
                                 archivo_detalle, ID_registro
  data/datasets/<archivo_detalle>.csv  →  CSV completo del dataset, con columna ID
  Un dataset = un CSV. Cada punto del índice tiene su ID_registro para buscar
  la fila exacta en el CSV del dataset.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import json, os, glob, unicodedata

app = FastAPI(title="SICAR Áncash API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Imágenes ──────────────────────────────────────────────────────────────────
_img = os.path.normpath(os.path.join(BASE_DIR, "..", "images"))
if not os.path.exists(_img):
    _img = os.path.join(BASE_DIR, "images")
    os.makedirs(_img, exist_ok=True)
_img = os.path.realpath(_img)
app.mount("/images", StaticFiles(directory=_img), name="images")
print(f"📁 Imágenes: {_img}  ({'OK' if os.path.exists(_img) else 'NO EXISTE'})")

# ── Utilidades CSV ────────────────────────────────────────────────────────────
def sep(ruta):
    try:
        with open(ruta, 'r', encoding='utf-8-sig') as f: l = f.readline()
        return ';' if l.count(';') > l.count(',') else ','
    except: return ','

def leer(ruta):
    df = pd.read_csv(ruta, dtype=str, sep=sep(ruta), encoding='utf-8-sig')
    df.fillna("", inplace=True)
    return df

# ── CSV ÍNDICE ────────────────────────────────────────────────────────────────
# Columnas requeridas: Tipo_Dataset, Cuenca, Provincia, Distrito, X, Y,
#                      archivo_detalle, ID_registro
# Compatibilidad: si no existe datos_index.csv, usa Datos_Visor_Ancash.csv
RUTA_IDX = os.path.join(BASE_DIR, "datos_index.csv")
if not os.path.exists(RUTA_IDX):
    RUTA_IDX = os.path.join(BASE_DIR, "Datos_Visor_Ancash.csv")
    print("⚠  datos_index.csv no encontrado — usando Datos_Visor_Ancash.csv")

try:
    df = leer(RUTA_IDX)

    if "Departamento" in df.columns:
        df["Departamento"] = (df["Departamento"]
            .str.replace("Á","A",case=False).str.strip().str.upper())
        df = df[df["Departamento"] == "ANCASH"]

    for col in ["Cuenca","Provincia","Distrito","Tipo_Dataset"]:
        if col in df.columns:
            df[col] = df[col].str.replace(r'\s+',' ',regex=True).str.strip().str.title()

    if "Tipo_Dataset" in df.columns:
        df["Tipo_Dataset"] = (df["Tipo_Dataset"]
            .str.replace("Rrss","RRSS").str.replace("Dar","DAR")
            .str.replace("Metales Cp","Metales CP"))

    for col_opt in ["archivo_detalle","ID_registro"]:
        if col_opt not in df.columns:
            df[col_opt] = ""

    print(f"✅ Índice: {len(df)} filas | cols: {list(df.columns)}")
    
except Exception as e:
    print(f"❌ Error índice: {e}"); df = pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════════════
# RESTRICCIÓN AL DEPARTAMENTO DE ÁNCASH
# ══════════════════════════════════════════════════════════════════════════════
# El índice de datos es de alcance nacional y NO trae columna "Departamento".
# Se aplican dos criterios combinados:
#   1) Criterio por nombre  — la provincia o el distrito deben figurar en las
#      listas oficiales INEI de Áncash (tomadas de los propios GeoJSON).
#   2) Criterio geométrico  — el punto debe caer dentro de limite_ancash.geojson
#      (requiere shapely; si no está disponible se aplica solo el criterio 1).
# Nunca se debe caer en un estado donde no se aplique ningún filtro.
# ══════════════════════════════════════════════════════════════════════════════

def norm_txt(s) -> str:
    """Normaliza: sin acentos, sin espacios repetidos, mayúsculas."""
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.replace("?", "N").split()).upper()

def _tokens(s):
    """Separa nombres compuestos tipo 'Aija / Recuay' → ['AIJA','RECUAY']."""
    return [t.strip() for t in norm_txt(s).split("/") if t.strip()]

def _nombres_geojson(archivo: str, propiedad: str) -> set:
    try:
        with open(os.path.join(BASE_DIR, archivo), "r", encoding="utf-8") as fh:
            g = json.load(fh)
        return {norm_txt(ft["properties"][propiedad])
                for ft in g.get("features", [])
                if ft.get("properties", {}).get(propiedad)}
    except Exception as e:
        print(f"⚠  No se pudieron leer nombres de {archivo}: {e}")
        return set()

PROV_ANCASH   = _nombres_geojson("limite_provincias.geojson", "PROVINCIA")
DIST_ANCASH   = _nombres_geojson("limite_distritos.geojson",  "DISTRITO")
CUENCA_ANCASH = _nombres_geojson("limite_cuencas.geojson",    "NOMBRE")

# Variantes de escritura encontradas en las fuentes → nombre oficial INEI
ALIAS_UBIGEO = {
    "CARLOS F. FITZCARRALD": "CARLOS FERMIN FITZCARRALD",
    "CARLOS FERMIN FITZCARRAL": "CARLOS FERMIN FITZCARRALD",
    "CHIMBOTE": "SANTA",          # Chimbote es capital de la provincia de Santa
    "MAR": "HUARMEY",             # registros marinos frente a Huarmey
    "NEPENA": "NEPEÑA",
}

def _canon(valor, oficiales: set) -> set:
    """Devuelve el conjunto de nombres oficiales que corresponden al valor."""
    out = set()
    for t in _tokens(valor):
        t = ALIAS_UBIGEO.get(t, t)
        t = norm_txt(t)
        if t in oficiales:
            out.add(t)
    return out

# Mapas índice_de_fila → conjunto de provincias / distritos oficiales
PROV_FILA: dict = {}
DIST_FILA: dict = {}

if not df.empty:
    antes = len(df)

    # ── Criterio 1: nombres oficiales ─────────────────────────────────────────
    col_prov = "Provincia" if "Provincia" in df.columns else None
    col_dist = "Distrito"  if "Distrito"  in df.columns else None

    provs = df[col_prov].map(lambda v: _canon(v, PROV_ANCASH)) if col_prov else pd.Series([set()] * len(df), index=df.index)
    dists = df[col_dist].map(lambda v: _canon(v, DIST_ANCASH)) if col_dist else pd.Series([set()] * len(df), index=df.index)

    tiene_texto = pd.Series(False, index=df.index)
    if col_prov: tiene_texto |= df[col_prov].astype(str).str.strip().ne("")
    if col_dist: tiene_texto |= df[col_dist].astype(str).str.strip().ne("")

    coincide_nombre = provs.map(bool) | dists.map(bool)
    # Se conserva la fila si sus nombres son de Áncash, o si no trae nombre alguno
    ok_nombre = coincide_nombre | (~tiene_texto)

    # ── Criterio 2: geometría del departamento ────────────────────────────────
    lat_col = next((c for c in ["Latitud", "Y"] if c in df.columns), None)
    lon_col = next((c for c in ["Longitud", "X"] if c in df.columns), None)
    if lat_col and lon_col:
        df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
        df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    ok_geo = pd.Series(True, index=df.index)
    try:
        import shapely
        from shapely.geometry import shape as _shape

        with open(os.path.join(BASE_DIR, "limite_ancash.geojson"), "r", encoding="utf-8") as fh:
            _g = json.load(fh)
        GEOM_ANCASH = shapely.union_all([_shape(ft["geometry"]) for ft in _g["features"]])
        shapely.prepare(GEOM_ANCASH)

        if lat_col and lon_col:
            validas = df[lat_col].notna() & df[lon_col].notna()
            sub = df[validas]
            dentro = shapely.intersects(
                GEOM_ANCASH,
                shapely.points(sub[lon_col].values, sub[lat_col].values)
            )
            ok_geo = pd.Series(False, index=df.index)
            ok_geo.loc[sub.index] = dentro
            print(f"✅ Filtro geométrico Áncash: {int(dentro.sum())} de {len(sub)} puntos con coordenadas")
    except ImportError:
        GEOM_ANCASH = None
        print("⚠  shapely no instalado — se aplica SOLO el filtro por nombres oficiales. "
              "Instálalo con: pip install shapely")
    except Exception as e:
        GEOM_ANCASH = None
        print(f"⚠  Filtro geométrico no aplicado ({e}) — se aplica SOLO el filtro por nombres.")

    # ── Combinación ───────────────────────────────────────────────────────────
    df = df[ok_nombre & ok_geo].copy()
    PROV_FILA = {i: provs[i] for i in df.index}
    DIST_FILA = {i: dists[i] for i in df.index}

    # Cuencas: restringir a las unidades hidrográficas presentes en Áncash
    if "Cuenca" in df.columns:
        cu_norm = df["Cuenca"].map(norm_txt)
        fuera = sorted({c for c in cu_norm.unique() if c and c not in CUENCA_ANCASH})
        if fuera:
            print(f"ℹ  {len(fuera)} unidades hidrográficas ajenas a Áncash quedan sin etiqueta de cuenca")
            df.loc[~cu_norm.isin(CUENCA_ANCASH), "Cuenca"] = ""

    print(f"✅ Restricción a Áncash: {antes} → {len(df)} registros "
          f"| {len({p for s in PROV_FILA.values() for p in s})} provincias "
          f"| {len({d for s in DIST_FILA.values() for d in s})} distritos")

def _mask_lista(indices, seleccion, mapa_filas):
    """Máscara booleana: la fila coincide si comparte algún nombre con la selección."""
    sel = set()
    for s in seleccion:
        sel |= _canon(s, PROV_ANCASH | DIST_ANCASH) or {norm_txt(s)}
    return [bool(sel & mapa_filas.get(i, set())) for i in indices]

def _titulo(n: str) -> str:
    """Nombre oficial en formato de presentación."""
    return " / ".join(p.strip().title() for p in n.split("/"))

# ── Cache de datasets detalle ──────────────────────────────────────────────────
_cache: dict = {}
DATASETS_DIR = os.path.join(BASE_DIR, "data", "datasets")
os.makedirs(DATASETS_DIR, exist_ok=True)

def get_dataset(nombre: str) -> pd.DataFrame:
    """Carga y cachea un CSV de dataset. nombre = nombre de archivo (sin ruta)."""
    if not nombre or not nombre.strip():
        return pd.DataFrame()
    if nombre in _cache:
        return _cache[nombre]
    ruta = os.path.join(DATASETS_DIR, nombre)
    if not os.path.exists(ruta):
        print(f"⚠  Dataset no encontrado: {ruta}")
        return pd.DataFrame()
    try:
        ds = leer(ruta)
        _cache[nombre] = ds
        print(f"📂 Dataset '{nombre}' cargado: {len(ds)} filas")
        return ds
    except Exception as e:
        print(f"❌ Error dataset '{nombre}': {e}")
        return pd.DataFrame()

# ── Modelos ────────────────────────────────────────────────────────────────────
class Filtros(BaseModel):
    tipo: List[str]
    cuenca: List[str]
    provincia: List[str]
    distrito: List[str]
    secundarios: Optional[dict] = {}  # Nuevo campo para recibir {"RIESGO": ["ALTO", "MEDIO"]}

class Consulta(BaseModel):
    pregunta: str

class DetalleReq(BaseModel):
    archivo_detalle: str
    id_registro: Optional[str] = None

# ── Filtros en cascada ─────────────────────────────────────────────────────────
def _uniq(col):
    return sorted([x for x in df[col].unique() if x]) if not df.empty and col in df.columns else []

def _uniq_oficial(mapa_filas: dict, indices=None) -> List[str]:
    """Nombres oficiales de Áncash realmente presentes en las filas indicadas."""
    idx = df.index if indices is None else indices
    presentes = set()
    for i in idx:
        presentes |= mapa_filas.get(i, set())
    return sorted(_titulo(n) for n in presentes)

@app.get("/api/filtros")
def get_filtros():
    return {"tipos": _uniq("Tipo_Dataset"),
            "cuencas": _uniq("Cuenca"),
            "provincias": _uniq_oficial(PROV_FILA),
            "distritos": _uniq_oficial(DIST_FILA)}

# ── Configuración de Filtros Secundarios ───────────────────────────────────────
# Aquí mapeas el Tipo_Dataset con el archivo físico y las columnas que quieres usar
FILTROS_SECUNDARIOS_CONF = {
    "PASIVOS AMBIENTALES MINEROS": {
        "archivo": "minem_pam.csv",
        "columnas": ["RIESGO"]  # Puedes agregar más columnas si lo necesitas en el futuro
    }
}

@app.post("/api/filtros-secundarios")
def get_filtros_secundarios(tipos: List[str]):
    """Devuelve los valores únicos de las columnas configuradas para los tipos seleccionados"""
    resultado = {}
    for t in tipos:
        t_upper = t.upper()
        if t_upper in FILTROS_SECUNDARIOS_CONF:
            conf = FILTROS_SECUNDARIOS_CONF[t_upper]
            ds = get_dataset(conf["archivo"])
            if not ds.empty:
                for col in conf["columnas"]:
                    if col in ds.columns:
                        # Extraer valores únicos ignorando vacíos/NaN
                        val_unicos = sorted([str(x).strip() for x in ds[col].unique() if pd.notna(x) and str(x).strip()])
                        if col not in resultado:
                            resultado[col] = []
                        resultado[col].extend(val_unicos)
                        resultado[col] = sorted(list(set(resultado[col]))) # Eliminar duplicados
    return resultado

def _filtrar_cuenca(dt, seleccion):
    if not seleccion or "Cuenca" not in dt.columns:
        return dt
    sel = {norm_txt(c) for c in seleccion}
    return dt[dt["Cuenca"].map(norm_txt).isin(sel)]

@app.post("/api/cascada")
def cascada(f: Filtros):
    dt = df.copy()
    if f.tipo:      dt = dt[dt["Tipo_Dataset"].str.upper().isin([t.upper() for t in f.tipo])]
    cu = sorted([x for x in dt["Cuenca"].unique() if x]) if "Cuenca" in dt.columns else []
    dt = _filtrar_cuenca(dt, f.cuenca)
    pr = _uniq_oficial(PROV_FILA, dt.index)
    if f.provincia: dt = dt[_mask_lista(dt.index, f.provincia, PROV_FILA)]
    di = _uniq_oficial(DIST_FILA, dt.index)
    return {"cuencas": cu, "provincias": pr, "distritos": di}

@app.post("/api/filtrar")
def filtrar(f: Filtros):
    dff = df.copy()
    if f.tipo:      dff = dff[dff["Tipo_Dataset"].str.upper().isin([t.upper() for t in f.tipo])]
    dff = _filtrar_cuenca(dff, f.cuenca)
    if f.provincia: dff = dff[_mask_lista(dff.index, f.provincia, PROV_FILA)]
    if f.distrito:  dff = dff[_mask_lista(dff.index, f.distrito,  DIST_FILA)]

    # --- NUEVA LÓGICA DE FILTROS SECUNDARIOS ---
    if f.secundarios:
        mascara_global = pd.Series(False, index=dff.index)
        filtro_aplicado = False

        for t_idx in dff["Tipo_Dataset"].unique():
            t_upper = str(t_idx).upper()
            mask_tipo = dff["Tipo_Dataset"] == t_idx
            
            if t_upper in FILTROS_SECUNDARIOS_CONF:
                conf = FILTROS_SECUNDARIOS_CONF[t_upper]
                ds = get_dataset(conf["archivo"])
                
                # Identificar si el usuario ha enviado filtros que aplican a este dataset específico
                filtros_aplicables = {k: v for k, v in f.secundarios.items() if k in conf["columnas"] and k in ds.columns and v}
                
                if filtros_aplicables and not ds.empty:
                    filtro_aplicado = True
                    ds_filtrado = ds.copy()
                    for col, vals in filtros_aplicables.items():
                        ds_filtrado = ds_filtrado[ds_filtrado[col].isin(vals)]
                    
                    col_id = next((c for c in ["ID_registro","ID","Id","id"] if c in ds_filtrado.columns), None)
                    if col_id and "ID_registro" in dff.columns:
                        ids_validos = set(ds_filtrado[col_id].astype(str).str.strip().str.split(".").str[0].tolist())
                        dff_id_norm = dff["ID_registro"].astype(str).str.strip().str.split(".").str[0]
                        
                        # Mantener los puntos de ESTE tipo que coincidan con los IDs válidos
                        mascara_global = mascara_global | (mask_tipo & dff_id_norm.isin(ids_validos))
                    else:
                        mascara_global = mascara_global | mask_tipo
                else:
                    mascara_global = mascara_global | mask_tipo
            else:
                # Si el dataset no tiene configuración secundaria, no se ve afectado y se mantiene
                mascara_global = mascara_global | mask_tipo
        
        if filtro_aplicado:
            dff = dff[mascara_global]

    return {"cantidad_total": len(dff), "puntos": dff.to_dict(orient="records")}

# ── Detalle de punto ───────────────────────────────────────────────────────────
@app.post("/api/detalle-punto")
def detalle_punto(req: DetalleReq):
    """
    Busca en el CSV del dataset la fila con ID == id_registro.
    Devuelve todos sus campos para mostrar en el panel de detalles.
    """
    ds = get_dataset(req.archivo_detalle)
    if ds.empty:
        return {"ok": False, "error": f"Dataset '{req.archivo_detalle}' no encontrado.",
                "campos": {}, "columnas": []}

    # DIAGNÓSTICO TEMPORAL — quitar después
    print(f"🔍 Buscando ID: '{req.id_registro}'")
    print(f"   Columnas: {list(ds.columns)}")
    col_id_test = next((c for c in ["ID","Id","id","ID_registro","id_registro"] if c in ds.columns), None)
    if col_id_test:
        print(f"   Columna ID encontrada: '{col_id_test}'")
        print(f"   Primeros 5 valores: {ds[col_id_test].head().tolist()}")
        print(f"   Tipos: {ds[col_id_test].dtype}")

    # Buscar por ID si se especificó
    if req.id_registro and req.id_registro.strip():
        col_id = next((c for c in ["ID_registro","ID","Id","id"] if c in ds.columns), None)
        if col_id:
            # Normalizar ambos lados: convertir a string, quitar espacios y decimales (.0)
            id_buscado = req.id_registro.strip().split(".")[0]
            ds["_id_norm"] = ds[col_id].astype(str).str.strip().str.split(".").str[0]
            fila = ds[ds["_id_norm"] == id_buscado]
            ds.drop(columns=["_id_norm"], inplace=True)
            if not fila.empty:
                return {"ok": True, "campos": fila.iloc[0].to_dict(),
                        "columnas": list(ds.columns)}

    # Si no hay ID o no se encontró, devuelve metadata del dataset
    return {"ok": False,
            "error": f"ID '{req.id_registro}' no encontrado en '{req.archivo_detalle}'.",
            "columnas": list(ds.columns), "total_registros": len(ds),
            "campos": {}}

@app.get("/api/datasets")
def listar_datasets():
    """Lista todos los CSVs disponibles en /data/datasets/"""
    archivos = glob.glob(os.path.join(DATASETS_DIR, "*.csv"))
    resultado = []
    for a in sorted(archivos):
        nombre = os.path.basename(a)
        ds = get_dataset(nombre)
        col_id = next((c for c in ["ID","Id","id"] if c in ds.columns), None)
        resultado.append({
            "archivo": nombre,
            "filas": len(ds),
            "columnas": list(ds.columns),
            "tiene_id": col_id is not None,
            "columna_id": col_id
        })
    return {"datasets": resultado}

# ── GeoJSON ────────────────────────────────────────────────────────────────────
def gjson(p):
    try:
        with open(os.path.join(BASE_DIR, p), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"type": "FeatureCollection", "features": []}

# ── Recorte de polígonos al departamento de Áncash ─────────────────────────────
# Las unidades hidrográficas nacionales (cuencas y subcuencas) se extienden
# mucho más allá del departamento. Se recortan una sola vez al arrancar para que
# al seleccionarlas en el visor no se dibujen desbordadas hacia otras regiones.
_geo_cache: dict = {}

def _recortar_a_ancash(archivo: str) -> dict:
    """Devuelve el GeoJSON con las geometrías intersecadas con Áncash."""
    if archivo in _geo_cache:
        return _geo_cache[archivo]

    original = gjson(archivo)
    if GEOM_ANCASH is None:
        _geo_cache[archivo] = original
        return original

    try:
        import shapely
        from shapely.geometry import shape as _shape, mapping as _mapping

        feats = []
        for ft in original.get("features", []):
            try:
                gm = _shape(ft["geometry"])
                if not gm.intersects(GEOM_ANCASH):
                    continue
                inter = gm.intersection(GEOM_ANCASH)
                if inter.is_empty:
                    continue
                feats.append({**ft, "geometry": _mapping(inter)})
            except Exception:
                feats.append(ft)   # ante cualquier duda se conserva el original
        recortado = {"type": "FeatureCollection", "features": feats}
        print(f"✂  {archivo}: {len(original.get('features', []))} → {len(feats)} features recortadas a Áncash")
        _geo_cache[archivo] = recortado
        return recortado
    except Exception as e:
        print(f"⚠  Recorte de {archivo} no aplicado: {e}")
        _geo_cache[archivo] = original
        return original

def _filtrar_features(geo: dict, propiedades: List[str], nombres: str) -> dict:
    """Filtra un FeatureCollection por nombre (parámetro opcional ?nombres=a,b,c)."""
    if not nombres.strip():
        return geo
    # Se aceptan tanto nombres simples como compuestos ("Aija / Recuay")
    buscados = set()
    for n in nombres.split(","):
        if not n.strip():
            continue
        v = norm_txt(n)
        buscados.add(v)
        buscados |= {t.strip() for t in v.split("/") if t.strip()}
    feats = []
    for ft in geo.get("features", []):
        props = ft.get("properties", {}) or {}
        valores = {norm_txt(props.get(p, "")) for p in propiedades if props.get(p)}
        # También se aceptan nombres compuestos del tipo "Aija / Recuay"
        for v in list(valores):
            valores |= {t for t in v.split("/") if t.strip()}
        if buscados & {v.strip() for v in valores}:
            feats.append(ft)
    return {"type": "FeatureCollection", "features": feats}

@app.get("/api/poligonos/ancash")
def g_ancash():    return gjson("limite_ancash.geojson")

@app.get("/api/poligonos/cuencas")
def g_cuencas(nombres: str = ""):
    return _filtrar_features(_recortar_a_ancash("limite_cuencas.geojson"),
                             ["NOMBRE", "CUENCA", "Nombre"], nombres)

@app.get("/api/poligonos/provincias")
def g_prov(nombres: str = ""):
    return _filtrar_features(gjson("limite_provincias.geojson"),
                             ["PROVINCIA", "NOM_PROV", "NOMBPROV"], nombres)

@app.get("/api/poligonos/distritos")
def g_dist(nombres: str = ""):
    return _filtrar_features(gjson("limite_distritos.geojson"),
                             ["DISTRITO", "NOM_DIST", "NOMBDIST"], nombres)

@app.get("/api/poligonos/subcuencas")
def g_subcuencas(cuencas: str = "", nombres: str = "", solo_nombres: int = 0):
    """
    Tres modos de uso:
      - ?cuencas=Cuenca+Santa,...&solo_nombres=1  → devuelve {"nombres": [...]} para poblar el dropdown
      - ?cuencas=Cuenca+Santa,...                 → GeoJSON de subcuencas que intersectan esas cuencas
      - ?nombres=Alto+Santa,Medio+Casma,...       → GeoJSON de subcuencas con esos nombres exactos
    """
    COLS_NOMBRE = ["Nombre_UH", "NOMBRE", "Nombre", "nombre"]

    def _nombre_de(ft):
        props = ft.get("properties", {}) or {}
        for c in COLS_NOMBRE:
            v = props.get(c)
            if v and str(v).strip() and str(v).strip().lower() != "none":
                return str(v).strip()
        return ""

    # Subcuencas ya recortadas al departamento (una sola vez, en caché)
    geo_sub = _recortar_a_ancash("limite_subcuencas.geojson")
    feats = geo_sub.get("features", [])

    try:
        # ── Modo A: subcuencas contenidas en las cuencas seleccionadas ─────────
        if cuencas.strip():
            geo_cu = _filtrar_features(
                _recortar_a_ancash("limite_cuencas.geojson"),
                ["NOMBRE", "CUENCA", "Nombre"], cuencas
            )
            padres = geo_cu.get("features", [])

            if padres:
                try:
                    import shapely
                    from shapely.geometry import shape as _shape

                    area = shapely.union_all([_shape(f["geometry"]) for f in padres])
                    shapely.prepare(area)
                    seleccion = []
                    for ft in feats:
                        try:
                            gm = _shape(ft["geometry"])
                            # Se exige solape real, no un simple contacto de bordes
                            if gm.intersects(area) and not gm.touches(area):
                                seleccion.append(ft)
                        except Exception:
                            continue
                    feats = seleccion
                except ImportError:
                    print("⚠  shapely no instalado — subcuencas sin recorte por cuenca padre")

            if solo_nombres:
                return {"nombres": sorted({_nombre_de(f) for f in feats if _nombre_de(f)})}
            return {"type": "FeatureCollection", "features": feats}

        # ── Modo B: subcuencas por nombre exacto ──────────────────────────────
        if nombres.strip():
            buscados = {norm_txt(n) for n in nombres.split(",") if n.strip()}
            feats = [f for f in feats if norm_txt(_nombre_de(f)) in buscados]
            if solo_nombres:
                return {"nombres": sorted({_nombre_de(f) for f in feats if _nombre_de(f)})}
            return {"type": "FeatureCollection", "features": feats}

        # ── Sin parámetros ────────────────────────────────────────────────────
        if solo_nombres:
            return {"nombres": sorted({_nombre_de(f) for f in feats if _nombre_de(f)})}
        return {"type": "FeatureCollection", "features": feats}

    except Exception as e:
        print(f"⚠  Subcuencas: {e}")
        if solo_nombres:
            return {"nombres": []}
        return {"type": "FeatureCollection", "features": feats}
@app.get("/api/acr")
def g_acr():       return gjson(os.path.join("data","acr.geojson"))
@app.get("/api/cuencas-sicar")
def g_csicar():    return gjson(os.path.join("data","cuencas_sicar.geojson"))

# ── Catálogo de capas externas ─────────────────────────────────────────────────
# Edita esta lista para añadir/quitar capas sin tocar el frontend.
# Tipos soportados: geojson_local | osm_overpass | wms | wfs | csv_coords
CAPAS = [
    {
        "id": "rios_osm",
        "nombre": "Ríos (OpenStreetMap)",
        "tipo": "osm_overpass",
        "query": '[out:json][timeout:25];(way["waterway"~"river|stream|canal"](bbox););out geom;',
        "color": "#2471a3", "weight": 2,
        "icono": "fa-water", "grupo": "Hidrografía",
        "descripcion": "Ríos y quebradas cargados dinámicamente según el área visible"
    },
    {
        "id": "acr",
        "nombre": "Área de Conservación Regional",
        "tipo": "geojson_local",
        "endpoint": "/api/acr",
        "color": "#1e8449", "fillColor": "#52c47a",
        "weight": 2.5, "fillOpacity": 0.2, "dashArray": "6,4",
        "icono": "fa-shield-halved", "grupo": "Conservación",
        "descripcion": "Polígono del ACR local"
    },
    {
        "id": "cuencas_sicar",
        "nombre": "Cuencas SICAR",
        "tipo": "geojson_local",
        "endpoint": "/api/cuencas-sicar",
        "color": "#0068c9", "fillColor": "#aed6f1",
        "weight": 2, "fillOpacity": 0.15,
        "icono": "fa-water", "grupo": "Cuencas",
        "descripcion": "Delimitación de cuencas del SICAR"
    },
]

@app.get("/api/capas-externas")
def get_capas():
    return {"capas": CAPAS}

# ── Iniciativas ────────────────────────────────────────────────────────────────
@app.get("/api/iniciativas")
def get_iniciativas():
    ruta = os.path.join(BASE_DIR, "data", "proyectos.csv")
    if not os.path.exists(ruta): return []
    try:
        dp = leer(ruta)
        for col in ["Lat","Long"]:
            if col in dp.columns:
                dp[col] = pd.to_numeric(dp[col], errors="coerce")
        if "Plantones" in dp.columns:
            dp["Plantones"] = pd.to_numeric(dp["Plantones"], errors="coerce").fillna(0)
        return dp.to_dict(orient="records")
    except Exception as e:
        print(f"❌ Iniciativas: {e}"); return []

# ── Chatbot ────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# TEMÁTICAS Y PRESETS DE EXPLORACIÓN GUIADA
# ══════════════════════════════════════════════════════════════════════════════
# Cada temática agrupa varios Tipo_Dataset y genera "presets": una combinación de
# filtros lista para aplicar más un dato destacado. TODAS las cifras se calculan
# sobre el índice real en memoria; no hay valores escritos a mano.
# ══════════════════════════════════════════════════════════════════════════════

TEMATICAS_CONF = [
    {
        "id": "agua", "nombre": "Agua", "icono": "fa-droplet", "color": "#0182c7",
        "descripcion": "Derechos de uso, monitoreo y fuentes contaminantes",
        "principal": "DERECHOS DE USO DE AGUA",
        "tipos": ["DERECHOS DE USO DE AGUA", "FUENTES CONTAMINANTES",
                  "PUNTOS DE MUESTREO ANA", "RED DE MONITOREO ANA",
                  "PUNTOS DE MUESTREO OEFA", "PUNTOS DE MUESTREO SENASA",
                  "PUNTOS CRÍTICOS", "ACREDITACIÓN DE DISPONIBILIDAD HÍDRICA",
                  "FORMALIZACIÓN DE DERECHOS DE USO"],
    },
    {
        "id": "mineria", "nombre": "Minería", "icono": "fa-helmet-safety", "color": "#a8730f",
        "descripcion": "Pasivos ambientales, unidades mineras y drenaje ácido",
        "principal": "PASIVOS AMBIENTALES MINEROS",
        "tipos": ["PASIVOS AMBIENTALES MINEROS", "GRAN Y MEDIANA MINERIA",
                  "PEQUENA MINERIA", "REINFOS", "SITIOS CONTAMINADOS CON DAR",
                  "UNIDADES FISCALIZABLES OEFA"],
    },
    {
        "id": "residuos", "nombre": "Residuos sólidos", "icono": "fa-trash-can", "color": "#2e8b57",
        "descripcion": "Áreas degradadas e infraestructura de disposición",
        "principal": "ADRS MUNICIPALES",
        "tipos": ["ADRS MUNICIPALES", "ADRS NO MUNICIPALES", "INFRAESTRUCTURA DE RRSS"],
    },
    {
        "id": "metales", "nombre": "Metales pesados", "icono": "fa-flask-vial", "color": "#b03060",
        "descripcion": "Población expuesta, dosajes y puntos de contaminación",
        "principal": "CENTROS POBLADOS CON MP",
        "tipos": ["CENTROS POBLADOS CON MP", "DOSAJES METALES CP",
                  "PUNTOS DE CONTAMINACION AMBIENTAL"],
    },
]

_tematicas_cache: Optional[dict] = None

def _conteo_por_provincia(sub) -> List[tuple]:
    acc: dict = {}
    for i in sub.index:
        for p in PROV_FILA.get(i, set()):
            acc[p] = acc.get(p, 0) + 1
    return sorted(acc.items(), key=lambda x: -x[1])

def _etiqueta_tipo(clave: str) -> str:
    """Devuelve el Tipo_Dataset tal como está escrito en el índice."""
    if df.empty or "Tipo_Dataset" not in df.columns:
        return clave
    coincide = df[df["Tipo_Dataset"].str.upper() == clave.upper()]["Tipo_Dataset"]
    return coincide.iloc[0] if not coincide.empty else clave

def _pct(parte: int, total: int) -> int:
    return round(parte * 100 / total) if total else 0

def _pct_fino(parte, total) -> str:
    """Porcentaje con un decimal cuando el valor es menor a 1, para no mostrar 0%."""
    if not total:
        return "0"
    v = parte * 100 / total
    if v < 1:
        return f"{v:.1f}".replace(".", ",")
    return str(round(v))

def _num(n) -> str:
    """Miles separados por espacio fino, sin tocar la puntuación de la frase."""
    return f"{int(n):,}".replace(",", " ")

def _millones(n) -> str:
    """Cifras muy grandes expresadas en una unidad legible."""
    n = float(n)
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}".replace(".", ",") + " mil millones"
    if n >= 1_000_000:
        return _num(round(n / 1_000_000)) + " millones"
    return _num(round(n))

# ââ Trazabilidad: fuente oficial y vigencia de cada conjunto de datos ââââââââââ
# El campo de fecha permite calcular el periodo real que cubre el archivo. Si un
# dataset no declara fecha, se dice explicitamente: es informacion que la
# Gerencia debe solicitar a la entidad generadora, no algo que se pueda suponer.
FUENTE_DATASET = {
    "DERECHOS DE USO DE AGUA": {
        "fuente": "ANA · Registro Administrativo de Derechos de Uso de Agua",
        "archivo": "ana_du_agua.csv", "campo_fecha": "Fecha Resolución"},
    "FUENTES CONTAMINANTES": {
        "fuente": "ANA · Inventario de Fuentes Contaminantes en cuerpos de agua",
        "archivo": "ana_fuentescontamin.csv", "campo_fecha": "Fecha Inicio de Identificación"},
    "PUNTOS DE MUESTREO ANA": {
        "fuente": "ANA · Puntos de muestreo de calidad de agua",
        "archivo": "ana_ptosmuestreo.csv", "campo_fecha": None},
    "RED DE MONITOREO ANA": {
        "fuente": "ANA · Red de monitoreo de calidad de los recursos hídricos",
        "archivo": "ana_redmonitoreo.csv", "campo_fecha": None},
    "PUNTOS DE MUESTREO OEFA": {
        "fuente": "OEFA · Puntos de muestreo de fiscalización ambiental",
        "archivo": "oefa_ptosmuestreo.csv", "campo_fecha": None},
    "PUNTOS DE MUESTREO SENASA": {
        "fuente": "SENASA · Puntos de muestreo",
        "archivo": "senasa_ptosmuestreo.csv", "campo_fecha": None},
    "ACREDITACION DE DISPONIBILIDAD HIDRICA": {
        "fuente": "ANA · Acreditaciones de disponibilidad hídrica (Visor de Cuencas)",
        "archivo": "ana_acreditacion_hidrica.csv", "campo_fecha": "Fecha de resolución"},
    "FORMALIZACION DE DERECHOS DE USO": {
        "fuente": "ANA · Formalización de derechos de uso de agua (Visor de Cuencas)",
        "archivo": "ana_formalizacion.csv", "campo_fecha": "Fecha de resolución"},
    "PUNTOS CRITICOS": {
        "fuente": "ANA · Puntos críticos por inundación, huaicos y erosión fluvial "
                  "(Plataforma Nacional de Datos Abiertos)",
        "archivo": "ana_puntoscriticos.csv", "campo_fecha": "Año de identificación"},
    "PASIVOS AMBIENTALES MINEROS": {
        "fuente": "MINEM · Inventario de Pasivos Ambientales Mineros",
        "archivo": "minem_pam.csv", "campo_fecha": None},
    "SITIOS CONTAMINADOS CON DAR": {
        "fuente": "INAIGEM · Sitios con Drenaje Ácido de Roca",
        "archivo": "inaigem_sitiosdar.csv", "campo_fecha": None},
    "REINFOS": {
        "fuente": "DREM Áncash · Registro Integral de Formalización Minera",
        "archivo": "drem_reinfos.csv", "campo_fecha": None},
    "UNIDADES FISCALIZABLES OEFA": {
        "fuente": "OEFA · Unidades fiscalizables",
        "archivo": "oefa_unidadfiscal.csv", "campo_fecha": None},
    "ADRS MUNICIPALES": {
        "fuente": "OEFA · Áreas degradadas por residuos sólidos municipales",
        "archivo": "oefa_adrs_municipal.csv", "campo_fecha": None},
    "ADRS NO MUNICIPALES": {
        "fuente": "OEFA · Áreas degradadas por residuos sólidos no municipales",
        "archivo": "oefa_adrs_nomunicipal.csv", "campo_fecha": None},
    "INFRAESTRUCTURA DE RRSS": {
        "fuente": "OEFA · Infraestructura de residuos sólidos",
        "archivo": "oefa_infraestructura_rrss.csv", "campo_fecha": None},
    "CENTROS POBLADOS CON MP": {
        "fuente": "DIRESA Áncash · Centros poblados con presencia de metales pesados",
        "archivo": "diresa_cp_mp.csv", "campo_fecha": None},
    "DOSAJES METALES CP": {
        "fuente": "DIRESA Áncash · Dosajes de metales pesados",
        "archivo": "Dosajes_CP.csv", "campo_fecha": None},
}

SIN_FECHA = "año no declarado en el archivo de origen"
_periodo_cache: dict = {}

def _periodo(tipo: str) -> str:
    """Rango de anios que cubre el dataset, calculado del propio archivo."""
    clave = norm_txt(tipo)
    if clave in _periodo_cache:
        return _periodo_cache[clave]
    conf = FUENTE_DATASET.get(clave)
    res = SIN_FECHA
    if conf and conf.get("campo_fecha") and conf.get("archivo"):
        try:
            ds = get_dataset(conf["archivo"])
            if not ds.empty and conf["campo_fecha"] in ds.columns:
                fechas = pd.to_datetime(ds[conf["campo_fecha"]], errors="coerce", dayfirst=True).dropna()
                if not fechas.empty:
                    a, b = int(fechas.min().year), int(fechas.max().year)
                    res = str(a) if a == b else f"{a}–{b}"
        except Exception:
            pass
    _periodo_cache[clave] = res
    return res

def _fuente(tipo: str) -> str:
    conf = FUENTE_DATASET.get(norm_txt(tipo))
    return conf["fuente"] if conf else "Fuente oficial no especificada"

def _detalle_de(tipo: str) -> pd.DataFrame:
    """Filas del dataset de detalle correspondientes a registros de Ancash."""
    conf = FUENTE_DATASET.get(norm_txt(tipo))
    if not conf or not conf.get("archivo") or df.empty:
        return pd.DataFrame()
    ds = get_dataset(conf["archivo"])
    if ds.empty or "ID_registro" not in ds.columns:
        return pd.DataFrame()
    idx = df[df["Tipo_Dataset"].map(norm_txt) == norm_txt(tipo)]
    if idx.empty:
        return pd.DataFrame()
    ids = set(idx["ID_registro"].astype(str).str.strip())
    return ds[ds["ID_registro"].astype(str).str.strip().isin(ids)]

def _presets_agua(conf: dict) -> List[dict]:
    """
    Recorrido narrativo del agua en Ancash: parte del panorama general de las
    unidades hidrograficas, pasa por el uso real del recurso y termina en las
    presiones identificadas y en las brechas de informacion.
    Todas las cifras salen de los archivos de la ANA cargados en el sistema.
    """
    if df.empty:
        return []

    up = df["Tipo_Dataset"].str.upper()
    vacio = {"tipo": [], "cuenca": [], "provincia": [], "distrito": [], "secundarios": {}}
    ps: List[dict] = []

    et_du = _etiqueta_tipo("DERECHOS DE USO DE AGUA")
    et_fc = _etiqueta_tipo("FUENTES CONTAMINANTES")
    et_rm = _etiqueta_tipo("RED DE MONITOREO ANA")
    et_pm = _etiqueta_tipo("PUNTOS DE MUESTREO ANA")
    tipos_agua = [_etiqueta_tipo(t) for t in conf["tipos"] if (up == t).any()]

    # ── 1. Panorama hidrografico ──────────────────────────────────────────────
    try:
        n_cuencas = len(gjson("limite_cuencas.geojson").get("features", []))
        n_subcuencas = len(_recortar_a_ancash("limite_subcuencas.geojson").get("features", []))
    except Exception:
        n_cuencas, n_subcuencas = 0, 0

    sub_agua = df[up.isin(conf["tipos"])]
    cu_con_datos = sub_agua[sub_agua["Cuenca"].astype(str).str.strip() != ""]["Cuenca"].nunique()

    ps.append({
        "titulo": "El mapa hidrográfico de Áncash",
        "dato": (f"El departamento se organiza en <b>{n_cuencas}</b> unidades hidrográficas "
                 f"y <b>{n_subcuencas}</b> subcuencas. El visor tiene información de agua "
                 f"cargada en <b>{cu_con_datos}</b> de ellas."),
        "detalle": ("Las unidades hidrográficas siguen la codificación Pfafstetter que emplea "
                    "la Autoridad Nacional del Agua para todo el país."),
        "metrica": {"valor": str(n_cuencas), "unidad": "unidades hidrográficas"},
        "fuente": "ANA · Delimitación de unidades hidrográficas del Perú (método Pfafstetter)",
        "periodo": SIN_FECHA,
        "filtros": {**vacio, "tipo": tipos_agua},
    })

    # ── 2 y 3. Derechos de uso: cantidad frente a volumen ─────────────────────
    du = _detalle_de("DERECHOS DE USO DE AGUA")
    if not du.empty and "Tipo Uso" in du.columns:
        conteo = du["Tipo Uso"].value_counts()
        top_uso, n_top = conteo.index[0], int(conteo.iloc[0])
        ps.append({
            "titulo": "En qué se usa el agua de Áncash",
            "dato": (f"De los <b>{_num(len(du))}</b> derechos de uso de agua otorgados en el "
                     f"departamento, <b>{_num(n_top)}</b> son de uso <b>{top_uso.lower()}</b>, "
                     f"es decir el <b>{_pct(n_top, len(du))}%</b> del total."),
            "detalle": " · ".join(f"{k}: {_num(v)}" for k, v in conteo.head(5).items()),
            "metrica": {"valor": f"{_pct(n_top, len(du))}%", "unidad": f"de uso {top_uso.lower()}"},
            "fuente": _fuente("DERECHOS DE USO DE AGUA"),
            "periodo": _periodo("DERECHOS DE USO DE AGUA"),
            "filtros": {**vacio, "tipo": [et_du]},
        })

        if "Volúmen Derecho (m³)" in du.columns:
            vol = pd.to_numeric(du["Volúmen Derecho (m³)"], errors="coerce")
            total_vol = float(vol.sum())
            por_uso = du.assign(_v=vol).groupby("Tipo Uso")["_v"].sum().sort_values(ascending=False)
            if total_vol > 0 and not por_uso.empty:
                uso_vol, v_vol = por_uso.index[0], float(por_uso.iloc[0])
                n_der = int((du["Tipo Uso"] == uso_vol).sum())
                ps.append({
                    "titulo": "El volumen cuenta otra historia",
                    "dato": (f"Solo <b>{_num(n_der)}</b> derechos de uso <b>{uso_vol.lower()}</b> "
                             f"({_pct_fino(n_der, len(du))}% del total) concentran el "
                             f"<b>{_pct(v_vol, total_vol)}%</b> del volumen de agua otorgado en "
                             f"Áncash: <b>{_millones(v_vol)}</b> de metros cúbicos al año."),
                    "detalle": " · ".join(f"{k}: {_millones(v)} m³"
                                              for k, v in por_uso.head(4).items()),
                    "metrica": {"valor": f"{_pct(v_vol, total_vol)}%", "unidad": "del volumen otorgado"},
                    "fuente": _fuente("DERECHOS DE USO DE AGUA"),
                    "periodo": _periodo("DERECHOS DE USO DE AGUA"),
                    "filtros": {**vacio, "tipo": [et_du]},
                })

    # ── 4. Red de monitoreo de calidad ────────────────────────────────────────
    rm = _detalle_de("RED DE MONITOREO ANA")
    col_tipo = next((c for c in ["TIPO DEL RECURSO HÍDRICO", "TIPO_RH"] if not rm.empty and c in rm.columns), None)
    if not rm.empty and col_tipo:
        cuerpos = rm[col_tipo].value_counts()
        ps.append({
            "titulo": "Dónde se vigila la calidad del agua",
            "dato": (f"La ANA mantiene <b>{_num(len(rm))}</b> puntos de monitoreo de calidad "
                     f"en Áncash, distribuidos principalmente en <b>{cuerpos.index[0].lower()}s</b> "
                     f"({_num(int(cuerpos.iloc[0]))} puntos)."),
            "detalle": " · ".join(f"{k}: {_num(v)}" for k, v in cuerpos.head(4).items()),
            "metrica": {"valor": _num(len(rm)), "unidad": "puntos de monitoreo"},
            "fuente": _fuente("RED DE MONITOREO ANA"),
            "periodo": _periodo("RED DE MONITOREO ANA"),
            "filtros": {**vacio, "tipo": [et_rm]},
        })

    # ── 5. Categorias ECA de los cuerpos de agua ──────────────────────────────
    pm = _detalle_de("PUNTOS DE MUESTREO ANA")
    col_cat = next((c for c in ["CLASIFICAC", "CLASIFICACÍON DE CUERPOS DE AGUA"]
                    if not pm.empty and c in pm.columns), None)
    if not pm.empty and col_cat:
        cats = pm[col_cat].value_counts()
        ps.append({
            "titulo": "Para qué está clasificada cada agua",
            "dato": (f"De los <b>{_num(len(pm))}</b> puntos de muestreo, <b>{_num(int(cats.iloc[0]))}</b> "
                     f"corresponden a cuerpos de agua de <b>{cats.index[0]}</b>. La categoría define "
                     f"qué estándar de calidad le resulta exigible a ese cuerpo de agua."),
            "detalle": ("Categoría 1: agua para consumo humano · Categoría 3: riego y bebida de "
                        "animales · Categoría 4: conservación del ambiente acuático."),
            "metrica": {"valor": _num(int(cats.iloc[0])), "unidad": str(cats.index[0]).lower()},
            "fuente": _fuente("PUNTOS DE MUESTREO ANA"),
            "periodo": _periodo("PUNTOS DE MUESTREO ANA"),
            "filtros": {**vacio, "tipo": [et_pm]},
        })

    # ââ 6. Mediciones de metales conservadas ââââââââââââââââââââââââââââââââââ
    # DELIBERADAMENTE NO se calculan excedencias del ECA. El archivo de origen no
    # declara fecha de muestreo, subcategoria ECA, ni si el metal es total o
    # disuelto, y 20 registros traen 0,00 en los cuatro metales a la vez, lo que
    # indica ausencia de medicion y no concentracion nula. Afirmar cumplimiento o
    # incumplimiento con esos vacios podria contradecir los informes oficiales de
    # la ANA. Se declara lo que hay y lo que falta.
    METALES = [("As", "arsénico"), ("Cd", "cadmio"), ("Pb", "plomo"), ("Hg", "mercurio")]
    if not pm.empty:
        cols_met = [(c, n) for c, n in METALES if f"{c}_ppm" in pm.columns]
        if cols_met:
            medidos = pd.Series(False, index=pm.index)
            for c, _ in cols_met:
                medidos |= pd.to_numeric(pm[f"{c}_ppm"], errors="coerce").fillna(0) > 0
            n_med = int(medidos.sum())
            if n_med:
                ps.append({
                    "titulo": "Mediciones de metales disponibles",
                    "dato": (f"El visor conserva las concentraciones medidas de "
                             f"<b>{', '.join(n for _, n in cols_met[:-1])} y {cols_met[-1][1]}</b> "
                             f"en <b>{_num(n_med)}</b> de los {_num(len(pm))} puntos de muestreo "
                             f"de la ANA en Áncash."),
                    "detalle": ("Los valores se muestran tal como figuran en el archivo de origen. "
                                "Su comparación con los Estándares de Calidad Ambiental requiere "
                                "conocer la subcategoría aplicable y la fecha de muestreo, datos que "
                                "el archivo no declara y que corresponde solicitar a la entidad "
                                "generadora."),
                    "metrica": {"valor": _num(n_med), "unidad": "puntos con mediciones"},
                    "fuente": _fuente("PUNTOS DE MUESTREO ANA"),
                    "periodo": _periodo("PUNTOS DE MUESTREO ANA"),
                    "filtros": {**vacio, "tipo": [et_pm]},
                })

    # ââ 6. Fuentes contaminantes identificadas ââââââââââââââââââââââââââââââââ
    fc = _detalle_de("FUENTES CONTAMINANTES")
    if not fc.empty:
        n_fc = len(fc)
        det, metrica, extra = [], None, ""
        if "Naturaleza FC" in fc.columns:
            nat = fc["Naturaleza FC"].value_counts()
            n_res = int(nat.get("Aguas Residuales", 0))
            if n_res:
                extra = (f" De ellas, <b>{_num(n_res)}</b> corresponden a vertimientos de "
                         f"<b>aguas residuales</b> a cuerpos de agua.")
                metrica = {"valor": _num(n_res), "unidad": "vertimientos de aguas residuales"}
        if "Tipo Fuente Contaminante" in fc.columns:
            det = [f"{k}: {_num(v)}" for k, v in fc["Tipo Fuente Contaminante"].value_counts().items()]
        cau = pd.to_numeric(fc.get("Caudal (l/s)", pd.Series(dtype=str)), errors="coerce")
        cau_txt = ""
        if cau.notna().any() and float(cau.sum()) > 0:
            cau_txt = (f" El caudal vertido registrado suma "
                       f"<b>{float(cau.sum()):.1f}</b>".replace(".", ",") + " litros por segundo.")
        ps.append({
            "titulo": "Presiones sobre el agua",
            "dato": (f"La ANA ha identificado <b>{_num(n_fc)}</b> fuentes contaminantes en cuerpos "
                     f"de agua de Áncash.{extra}{cau_txt}"),
            "detalle": " · ".join(det),
            "metrica": metrica or {"valor": _num(n_fc), "unidad": "fuentes contaminantes"},
            "fuente": _fuente("FUENTES CONTAMINANTES"),
            "periodo": _periodo("FUENTES CONTAMINANTES"),
            "filtros": {**vacio, "tipo": [et_fc]},
        })

        # ── 7. Brecha de informacion ──────────────────────────────────────────
        col_uh = next((c for c in ["Unidad Hidrográfica", "NombreUH"] if c in fc.columns), None)
        if col_uh and n_cuencas:
            inventariadas = sorted({str(x).strip() for x in fc[col_uh] if str(x).strip()})
            if 0 < len(inventariadas) < n_cuencas:
                ps.append({
                    "titulo": "Lo que todavía no se ha inventariado",
                    "dato": (f"El inventario de fuentes contaminantes cubre <b>{len(inventariadas)}</b> "
                             f"de las <b>{n_cuencas}</b> unidades hidrográficas del departamento. "
                             f"Las demás no cuentan con un inventario cargado en el sistema, "
                             f"lo que no significa que estén libres de presiones."),
                    "detalle": "Unidades con inventario: " + " · ".join(inventariadas),
                    "metrica": {"valor": f"{len(inventariadas)}/{n_cuencas}",
                                "unidad": "unidades con inventario"},
                    "fuente": _fuente("FUENTES CONTAMINANTES"),
                    "periodo": _periodo("FUENTES CONTAMINANTES"),
                    "filtros": {**vacio, "tipo": [et_fc]},
                })

    # ââ Puntos criticos por peligro hidrico âââââââââââââââââââââââââââââââââââ
    # Se reportan conteos y distribucion temporal. NO se suman presupuestos ni
    # familias declaradas: el archivo de origen no define si esos campos son
    # poblacion expuesta o beneficiaria, ni si los anios son acumulativos.
    pc = _detalle_de("PUNTOS CRÍTICOS")
    if not pc.empty:
        col_anio = "Año de identificación"
        anios = pc[col_anio].astype(str).str.strip() if col_anio in pc.columns else pd.Series(dtype=str)
        anios = anios[anios != ""]
        rango, det = "", ""
        if not anios.empty:
            rango = (f" entre {anios.min()} y {anios.max()}"
                     if anios.min() != anios.max() else f" en {anios.min()}")
            det = "Puntos identificados por año — " + " · ".join(
                f"{k}: {_num(v)}" for k, v in anios.value_counts().sort_index().items())
        ps.append({
            "titulo": "Puntos críticos por peligro hídrico",
            "dato": (f"La ANA ha identificado <b>{_num(len(pc))}</b> puntos críticos en ríos y "
                     f"quebradas de Áncash{rango}: tramos con alta probabilidad de afectación a "
                     f"la población o a actividades económicas por inundación, activación de "
                     f"quebradas o erosión fluvial."),
            "detalle": det,
            "metrica": {"valor": _num(len(pc)), "unidad": "puntos críticos"},
            "fuente": _fuente("PUNTOS CRÍTICOS"),
            "periodo": _periodo("PUNTOS CRÍTICOS"),
            "filtros": {**vacio, "tipo": [_etiqueta_tipo("PUNTOS CRÍTICOS")]},
        })

    # ââ Drenaje acido de roca: donde es mas probable y cuanto se vigila âââââââ
    # IMPORTANTE: el dataset del INAIGEM es un MODELO DE PROBABILIDAD basado en
    # litologia y unidades geologicas (Prob_DAR entre 0,75 y 0,86), no una
    # medicion de contaminacion. El texto lo dice de forma explicita y no
    # atribuye contaminacion a ningun cuerpo de agua. El cruce que si es
    # defendible es de COBERTURA DE MONITOREO, no de niveles medidos.
    dar_idx = df[up_todos == "SITIOS CONTAMINADOS CON DAR"] if "up_todos" in dir() else df[df["Tipo_Dataset"].str.upper() == "SITIOS CONTAMINADOS CON DAR"]
    if not dar_idx.empty:
        try:
            import shapely
            from shapely.geometry import shape as _shape

            subs = _recortar_a_ancash("limite_subcuencas.geojson").get("features", [])
            def _nom_sub(ft):
                for c in ("Nombre_UH", "NOMBRE", "Nombre"):
                    v = (ft.get("properties") or {}).get(c)
                    if v and str(v).strip().lower() != "none":
                        return str(v).strip()
                return ""

            pts_dar = shapely.points(dar_idx["Longitud"].values, dar_idx["Latitud"].values)
            mejor, n_mejor, geom_mejor = "", 0, None
            for ft in subs:
                nb = _nom_sub(ft)
                if not nb or nb.lower().startswith("unidad hidrografica"):
                    continue
                gm = _shape(ft["geometry"])
                shapely.prepare(gm)
                n = int(shapely.intersects(gm, pts_dar).sum())
                if n > n_mejor:
                    mejor, n_mejor, geom_mejor = nb, n, gm

            if mejor and n_mejor:
                def _en(tipo):
                    ss = df[df["Tipo_Dataset"].str.upper() == tipo]
                    if ss.empty:
                        return 0
                    return int(shapely.intersects(
                        geom_mejor, shapely.points(ss["Longitud"].values, ss["Latitud"].values)).sum())
                n_mon = _en("RED DE MONITOREO ANA")
                n_pam = _en("PASIVOS AMBIENTALES MINEROS")
                extra = ""
                if n_mon:
                    extra = (f" En esa misma subcuenca la ANA mantiene <b>{_num(n_mon)}</b> puntos "
                             f"de la red de monitoreo de calidad del agua")
                    if n_pam:
                        extra += f" y el MINEM registra <b>{_num(n_pam)}</b> pasivos ambientales mineros"
                    extra += "."
                ps.append({
                    "titulo": "Dónde el drenaje ácido de roca es más probable",
                    "dato": (f"La subcuenca <b>{mejor}</b> concentra <b>{_num(n_mejor)}</b> de los "
                             f"{_num(len(dar_idx))} sitios que el INAIGEM identifica con alta "
                             f"probabilidad de generar drenaje ácido de roca en Áncash "
                             f"({_pct(n_mejor, len(dar_idx))}% del total).{extra}"),
                    "detalle": ("El drenaje ácido de roca es un proceso natural que la actividad minera "
                                "puede acelerar, y libera metales al agua. La capa del INAIGEM es un "
                                "modelo de probabilidad construido a partir de la litología y las "
                                "unidades geológicas: señala dónde el fenómeno es más probable, "
                                "no constituye una medición de contaminación."),
                    "metrica": {"valor": _num(n_mejor), "unidad": "sitios con alta probabilidad"},
                    "fuente": _fuente("SITIOS CONTAMINADOS CON DAR"),
                    "periodo": _periodo("SITIOS CONTAMINADOS CON DAR"),
                    "filtros": {**vacio, "tipo": [_etiqueta_tipo("SITIOS CONTAMINADOS CON DAR")]},
                })
        except ImportError:
            pass
        except Exception as e:
            print(f"⚠  Preset DAR no generado: {e}")

    # ── 8. Provincia con mayor concentracion ──────────────────────────────────
    sub_du = df[up == "DERECHOS DE USO DE AGUA"]
    prov = _conteo_por_provincia(sub_du)
    if prov:
        nombre_pr, n_pr = prov[0]
        ps.append({
            "titulo": "Provincia con más derechos otorgados",
            "dato": (f"<b>{_titulo(nombre_pr)}</b> concentra <b>{_num(n_pr)}</b> de los "
                     f"{_num(len(sub_du))} derechos de uso de agua registrados en Áncash."),
            "detalle": " · ".join(f"{_titulo(k)}: {_num(v)}" for k, v in prov[:4]),
            "metrica": {"valor": _num(n_pr), "unidad": "derechos de uso"},
            "fuente": _fuente("DERECHOS DE USO DE AGUA"),
            "periodo": _periodo("DERECHOS DE USO DE AGUA"),
            "filtros": {**vacio, "tipo": [et_du], "provincia": [_titulo(nombre_pr)]},
        })

    for n, p in enumerate(ps, start=1):
        p["id"] = f"agua-{n}"
        p["tema"] = "agua"
    return ps

def _presets_tema(conf: dict) -> List[dict]:
    """Construye los presets de una temática a partir de los datos reales."""
    if df.empty:
        return []

    if conf["id"] == "agua":
        return _presets_agua(conf)

    up = df["Tipo_Dataset"].str.upper()
    tipos_presentes = [t for t in conf["tipos"] if (up == t).any()]
    if not tipos_presentes:
        return []

    etiquetas = [_etiqueta_tipo(t) for t in tipos_presentes]
    principal_conf = conf["principal"] if conf["principal"] in tipos_presentes else tipos_presentes[0]
    sub = df[up.isin(tipos_presentes)]
    total = len(sub)
    presets: List[dict] = []
    vacio = {"tipo": [], "cuenca": [], "provincia": [], "distrito": [], "secundarios": {}}

    # ── 1. Panorama general de la temática ────────────────────────────────────
    prov = _conteo_por_provincia(sub)
    desglose = sub["Tipo_Dataset"].value_counts()
    presets.append({
        "titulo": f"Panorama de {conf['nombre'].lower()} en Áncash",
        "dato": (f"El visor reúne <b>{_num(total)}</b> registros de {conf['nombre'].lower()} "
                 f"en Áncash, provenientes de {len(tipos_presentes)} conjuntos de datos distintos."),
        "detalle": " · ".join(f"{k}: {_num(v)}" for k, v in desglose.head(4).items()),
        "metrica": {"valor": _num(total), "unidad": "registros"},
        "fuente": _fuente(principal_conf), "periodo": _periodo(principal_conf),
        "filtros": {**vacio, "tipo": etiquetas},
    })

    # ── 2. Unidad hidrográfica con mayor concentración ────────────────────────
    principal = conf["principal"] if conf["principal"] in tipos_presentes else tipos_presentes[0]
    etiqueta_pri = _etiqueta_tipo(principal)
    sub_pri = df[up == principal]
    cu = sub_pri[sub_pri["Cuenca"].astype(str).str.strip() != ""]["Cuenca"].value_counts()
    if not cu.empty:
        nombre_cu, n_cu = cu.index[0], int(cu.iloc[0])
        presets.append({
            "titulo": "Unidad hidrográfica con más registros",
            "dato": (f"La <b>{nombre_cu}</b> concentra <b>{_num(n_cu)}</b> de los "
                     f"{_num(len(sub_pri))} registros de «{etiqueta_pri}» del "
                     f"departamento, es decir el <b>{_pct(n_cu, len(sub_pri))}%</b>."),
            "detalle": " · ".join(f"{k}: {_num(v)}" for k, v in cu.head(4).items()),
            "metrica": {"valor": _num(n_cu), "unidad": etiqueta_pri},
            "fuente": _fuente(principal), "periodo": _periodo(principal),
            "filtros": {**vacio, "tipo": [etiqueta_pri], "cuenca": [nombre_cu]},
        })

    # ── 3. Provincia con mayor concentración ──────────────────────────────────
    prov_pri = _conteo_por_provincia(sub_pri)
    if prov_pri:
        nombre_pr, n_pr = prov_pri[0]
        presets.append({
            "titulo": "Provincia con mayor concentración",
            "dato": (f"<b>{_titulo(nombre_pr)}</b> es la provincia con más registros de "
                     f"«{etiqueta_pri}»: <b>{_num(n_pr)}</b> del total de "
                     f"{_num(len(sub_pri))} en Áncash."),
            "detalle": " · ".join(f"{_titulo(k)}: {_num(v)}" for k, v in prov_pri[:4]),
            "metrica": {"valor": _num(n_pr), "unidad": etiqueta_pri},
            "fuente": _fuente(principal), "periodo": _periodo(principal),
            "filtros": {**vacio, "tipo": [etiqueta_pri], "provincia": [_titulo(nombre_pr)]},
        })

    # ── 4. Dato específico por temática ───────────────────────────────────────
    if conf["id"] == "mineria":
        ds = get_dataset("minem_pam.csv")
        if not ds.empty and "RIESGO" in ds.columns:
            criticos = ["Alto", "Muy alto"]
            ids = set(ds[ds["RIESGO"].isin(criticos)]["ID_registro"]
                      .astype(str).str.strip().str.split(".").str[0]) \
                  if "ID_registro" in ds.columns else set()
            pam = df[up == "PASIVOS AMBIENTALES MINEROS"]
            if ids and "ID_registro" in pam.columns:
                norm_id = pam["ID_registro"].astype(str).str.strip().str.split(".").str[0]
                n = int(norm_id.isin(ids).sum())
                if n:
                    presets.append({
                        "titulo": "Pasivos de riesgo alto y muy alto",
                        "dato": (f"De los {_num(len(pam))} pasivos ambientales mineros registrados "
                                 f"en Áncash, <b>{n}</b> están clasificados con riesgo "
                                 f"<b>alto o muy alto</b> ({_pct(n, len(pam))}% del total)."),
                        "detalle": "Clasificación de riesgo según el inventario del MINEM.",
                        "metrica": {"valor": str(n), "unidad": "pasivos críticos"},
                        "fuente": _fuente("PASIVOS AMBIENTALES MINEROS"),
                        "periodo": _periodo("PASIVOS AMBIENTALES MINEROS"),
                        "filtros": {**vacio, "tipo": [_etiqueta_tipo("PASIVOS AMBIENTALES MINEROS")],
                                    "secundarios": {"RIESGO": criticos}},
                    })

    if conf["id"] == "residuos":
        n_deg = int((up == "ADRS MUNICIPALES").sum()) + int((up == "ADRS NO MUNICIPALES").sum())
        n_for = int((up == "INFRAESTRUCTURA DE RRSS").sum())
        if n_deg and n_for:
            presets.append({
                "titulo": "Brecha entre botaderos e infraestructura formal",
                "dato": (f"Áncash registra <b>{n_deg}</b> áreas degradadas por residuos sólidos "
                         f"frente a solo <b>{n_for}</b> instalaciones formales de disposición "
                         f"y tratamiento: <b>{round(n_deg/n_for, 1)} botaderos por cada "
                         f"infraestructura formal</b>."),
                "detalle": "Áreas degradadas municipales y no municipales según el OEFA.",
                "metrica": {"valor": f"{round(n_deg/n_for, 1)}×", "unidad": "botaderos por instalación"},
                "fuente": _fuente("ADRS MUNICIPALES"), "periodo": _periodo("ADRS MUNICIPALES"),
                "filtros": {**vacio, "tipo": [_etiqueta_tipo("ADRS MUNICIPALES"),
                                              _etiqueta_tipo("ADRS NO MUNICIPALES"),
                                              _etiqueta_tipo("INFRAESTRUCTURA DE RRSS")]},
            })

    if conf["id"] == "metales":
        cp = df[up == "CENTROS POBLADOS CON MP"]
        if not cp.empty:
            pr = _conteo_por_provincia(cp)
            n_prov = len({p for i in cp.index for p in PROV_FILA.get(i, set())})
            presets.append({
                "titulo": "Centros poblados con presencia de metales",
                "dato": (f"Se han identificado <b>{len(cp)}</b> centros poblados con presencia "
                         f"de metales pesados, distribuidos en <b>{n_prov}</b> provincias "
                         f"de Áncash."),
                "detalle": " · ".join(f"{_titulo(k)}: {v}" for k, v in pr[:4]),
                "metrica": {"valor": str(len(cp)), "unidad": "centros poblados"},
                "fuente": _fuente("CENTROS POBLADOS CON MP"), "periodo": _periodo("CENTROS POBLADOS CON MP"),
                "filtros": {**vacio, "tipo": [_etiqueta_tipo("CENTROS POBLADOS CON MP")]},
            })

    for n, p in enumerate(presets, start=1):
        p["id"] = f"{conf['id']}-{n}"
        p["tema"] = conf["id"]
        p.setdefault("fuente", _fuente(principal_conf))
        p.setdefault("periodo", _periodo(principal_conf))
    return presets

@app.get("/api/tematicas")
def get_tematicas():
    """Temáticas con sus presets de filtros y datos destacados calculados."""
    global _tematicas_cache
    if _tematicas_cache is not None:
        return _tematicas_cache

    temas = []
    for conf in TEMATICAS_CONF:
        presets = _presets_tema(conf)
        if not presets:
            continue
        up = df["Tipo_Dataset"].str.upper() if not df.empty else pd.Series(dtype=str)
        temas.append({
            "id": conf["id"], "nombre": conf["nombre"], "icono": conf["icono"],
            "color": conf["color"], "descripcion": conf["descripcion"],
            "total": int(up.isin([t for t in conf["tipos"]]).sum()) if not df.empty else 0,
            "presets": presets,
        })
    _tematicas_cache = {"tematicas": temas}
    print(f"✅ Temáticas: {len(temas)} temas, "
          f"{sum(len(t['presets']) for t in temas)} presets generados")
    return _tematicas_cache

# ══════════════════════════════════════════════════════════════════════════════
# REPORTE PDF POR ÁMBITO TERRITORIAL
# ══════════════════════════════════════════════════════════════════════════════
# Genera un informe ejecutivo del panorama ambiental de un distrito, provincia o
# unidad hidrográfica. Cubre SIEMPRE todos los datasets disponibles en ese
# ámbito, con independencia de los filtros de tipo activos en el visor.
# ══════════════════════════════════════════════════════════════════════════════

ENTIDAD_POR_TIPO = {
    "DERECHOS DE USO DE AGUA":           "Autoridad Nacional del Agua (ANA)",
    "FUENTES CONTAMINANTES":             "Autoridad Nacional del Agua (ANA)",
    "PUNTOS DE MUESTREO ANA":            "Autoridad Nacional del Agua (ANA)",
    "RED DE MONITOREO ANA":              "Autoridad Nacional del Agua (ANA)",
    "CENTROS POBLADOS CON MP":           "Dirección Regional de Salud Áncash (DIRESA)",
    "DOSAJES METALES CP":                "Dirección Regional de Salud Áncash (DIRESA)",
    "GRAN Y MEDIANA MINERIA":            "Dirección Regional de Energía y Minas (DREM)",
    "PEQUENA MINERIA":                   "Dirección Regional de Energía y Minas (DREM)",
    "REINFOS":                           "Dirección Regional de Energía y Minas (DREM)",
    "SITIOS CONTAMINADOS CON DAR":       "Instituto Nacional de Investigación en Glaciares (INAIGEM)",
    "PUNTOS DE CONTAMINACION AMBIENTAL": "Instituto Peruano de Fiscalización y Control Ambiental",
    "PASIVOS AMBIENTALES MINEROS":       "Ministerio de Energía y Minas (MINEM)",
    "ADRS MUNICIPALES":                  "Organismo de Evaluación y Fiscalización Ambiental (OEFA)",
    "ADRS NO MUNICIPALES":               "Organismo de Evaluación y Fiscalización Ambiental (OEFA)",
    "INFRAESTRUCTURA DE RRSS":           "Organismo de Evaluación y Fiscalización Ambiental (OEFA)",
    "PUNTOS DE MUESTREO OEFA":           "Organismo de Evaluación y Fiscalización Ambiental (OEFA)",
    "UNIDADES FISCALIZABLES OEFA":       "Organismo de Evaluación y Fiscalización Ambiental (OEFA)",
    "PUNTOS DE MUESTREO SENASA":         "Servicio Nacional de Sanidad Agraria (SENASA)",
    "PUNTOS CRITICOS":                   "Autoridad Nacional del Agua (ANA)",
    "ACREDITACION DE DISPONIBILIDAD HIDRICA": "Autoridad Nacional del Agua (ANA)",
    "FORMALIZACION DE DERECHOS DE USO":   "Autoridad Nacional del Agua (ANA)",
}

class ReporteReq(BaseModel):
    ambito: str            # "distrito" | "provincia" | "cuenca"
    valor: str

_logo_cache: dict = {}     # logos reescalados, para no incrustar los originales

def _sub_ambito(ambito: str, valor: str):
    """Subconjunto del índice para el ámbito solicitado."""
    if df.empty:
        return df
    if ambito == "distrito":
        return df[_mask_lista(df.index, [valor], DIST_FILA)]
    if ambito == "provincia":
        return df[_mask_lista(df.index, [valor], PROV_FILA)]
    if ambito == "cuenca":
        return df[df["Cuenca"].map(norm_txt) == norm_txt(valor)]
    return df.iloc[0:0]

@app.get("/api/reporte/ambitos")
def reporte_ambitos():
    """Ámbitos disponibles para reportar (uso informativo del frontend)."""
    return {
        "distritos":  _uniq_oficial(DIST_FILA),
        "provincias": _uniq_oficial(PROV_FILA),
        "cuencas":    _uniq("Cuenca"),
    }

@app.post("/api/reporte")
def reporte_pdf(req: ReporteReq):
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    import io, unicodedata as _ud
    from datetime import datetime

    ambito = (req.ambito or "").strip().lower()
    valor  = (req.valor or "").strip()
    if ambito not in ("distrito", "provincia", "cuenca") or not valor:
        raise HTTPException(status_code=400, detail="Ámbito o valor no válido.")

    sub = _sub_ambito(ambito, valor)
    if sub.empty:
        raise HTTPException(status_code=404,
                            detail=f"No hay registros para {ambito} «{valor}».")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
        from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                        Spacer, Table, TableStyle, Image, KeepTogether)
        from reportlab.graphics.shapes import Drawing, String, Rect
        from reportlab.graphics.charts.barcharts import HorizontalBarChart
        from reportlab.graphics.charts.piecharts import Pie
    except ImportError:
        raise HTTPException(status_code=503,
                            detail="La generación de reportes requiere reportlab en el servidor.")

    AZUL   = colors.HexColor("#0182c7")
    OSCURO = colors.HexColor("#12283a")
    GRIS   = colors.HexColor("#5a6b7a")
    SUAVE  = colors.HexColor("#f2f7fb")
    PALETA = [colors.HexColor(c) for c in
              ["#0182c7", "#2e8b57", "#a8730f", "#b03060", "#7c3aed",
               "#e8743b", "#1fb6a6", "#4d8ef7", "#d64550", "#6b7280"]]

    ss = getSampleStyleSheet()
    est_titulo   = ParagraphStyle("t1", parent=ss["Title"], fontSize=19, leading=23,
                                  textColor=OSCURO, spaceAfter=2)
    est_subtit   = ParagraphStyle("t2", parent=ss["Normal"], fontSize=10.5, leading=14,
                                  textColor=GRIS, alignment=TA_CENTER)
    est_seccion  = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, leading=16,
                                  textColor=AZUL, spaceBefore=13, spaceAfter=6)
    est_texto    = ParagraphStyle("p", parent=ss["Normal"], fontSize=9.6, leading=14,
                                  textColor=colors.HexColor("#33475b"), alignment=TA_JUSTIFY)
    est_celda    = ParagraphStyle("td", parent=ss["Normal"], fontSize=8.4, leading=11)
    est_celda_b  = ParagraphStyle("th", parent=est_celda, textColor=colors.white,
                                  fontName="Helvetica-Bold")
    est_nota     = ParagraphStyle("nota", parent=ss["Normal"], fontSize=7.8, leading=10.5,
                                  textColor=colors.HexColor("#8b98a5"))

    etiqueta_ambito = {"distrito": "Distrito", "provincia": "Provincia",
                       "cuenca": "Unidad hidrográfica"}[ambito]
    hoy = datetime.now().strftime("%d/%m/%Y")

    # ── Datos base ────────────────────────────────────────────────────────────
    total = len(sub)
    por_tipo = sub["Tipo_Dataset"].value_counts()
    entidades = sorted({ENTIDAD_POR_TIPO.get(norm_txt(t), "Otras fuentes")
                        for t in por_tipo.index})

    up_sub = sub["Tipo_Dataset"].str.upper()
    resumen_tema = []
    for conf in TEMATICAS_CONF:
        n = int(up_sub.isin(conf["tipos"]).sum())
        if n:
            resumen_tema.append((conf["nombre"], n, conf["color"]))
    resumen_tema.sort(key=lambda x: -x[1])

    # Desagregación territorial según el ámbito
    if ambito == "provincia":
        titulo_desg, desg = "Distribución por distrito", {}
        for i in sub.index:
            for d in DIST_FILA.get(i, set()):
                desg[_titulo(d)] = desg.get(_titulo(d), 0) + 1
    elif ambito == "cuenca":
        titulo_desg, desg = "Distribución por provincia", {}
        for i in sub.index:
            for p in PROV_FILA.get(i, set()):
                desg[_titulo(p)] = desg.get(_titulo(p), 0) + 1
    else:
        titulo_desg = "Distribución por unidad hidrográfica"
        desg = {k: int(v) for k, v in
                sub[sub["Cuenca"].astype(str).str.strip() != ""]["Cuenca"]
                .value_counts().items()}
    desg = dict(sorted(desg.items(), key=lambda x: -x[1])[:8])

    # Riesgo de pasivos mineros, si aplica
    riesgo_pam = {}
    pam_sub = sub[up_sub == "PASIVOS AMBIENTALES MINEROS"]
    if not pam_sub.empty:
        ds = get_dataset("minem_pam.csv")
        if not ds.empty and "RIESGO" in ds.columns and "ID_registro" in ds.columns:
            ids = pam_sub["ID_registro"].astype(str).str.strip().str.split(".").str[0]
            dsn = ds.copy()
            dsn["_id"] = dsn["ID_registro"].astype(str).str.strip().str.split(".").str[0]
            sel = dsn[dsn["_id"].isin(set(ids))]
            if not sel.empty:
                riesgo_pam = {k: int(v) for k, v in sel["RIESGO"].value_counts().items()}

    # ── Utilidades de dibujo ──────────────────────────────────────────────────
    def barras(datos: dict, ancho=170*mm, alto_barra=13):
        """Gráfico de barras horizontales con etiqueta y valor."""
        items = list(datos.items())
        n = len(items)
        alto = max(38, n * alto_barra + 26)
        d = Drawing(ancho, alto)
        maxv = max(datos.values()) if datos else 1
        etiqueta_ancho = 62*mm
        barra_max = ancho - etiqueta_ancho - 22*mm
        for k, (nombre, val) in enumerate(items):
            y = alto - 18 - k * alto_barra
            corto = nombre if len(nombre) <= 34 else nombre[:32] + "…"
            d.add(String(0, y, corto, fontName="Helvetica", fontSize=7.6,
                         fillColor=colors.HexColor("#33475b")))
            w = max(1.5, (val / maxv) * barra_max)
            d.add(Rect(etiqueta_ancho, y - 2.4, w, 8.4,
                       fillColor=PALETA[k % len(PALETA)], strokeColor=None))
            d.add(String(etiqueta_ancho + w + 4, y, f"{val:,}".replace(",", " "),
                         fontName="Helvetica-Bold", fontSize=7.6, fillColor=OSCURO))
        return d

    def dona(datos: dict, ancho=85*mm, alto=52*mm):
        d = Drawing(ancho, alto)
        p = Pie()
        p.x, p.y = 6, 4
        p.width = p.height = 44*mm
        p.data = list(datos.values())
        p.labels = None
        p.innerRadiusFraction = 0.55
        p.slices.strokeColor = colors.white
        p.slices.strokeWidth = 1.4
        for i in range(len(datos)):
            p.slices[i].fillColor = PALETA[i % len(PALETA)]
        d.add(p)
        tot = sum(datos.values()) or 1
        for i, (k, v) in enumerate(datos.items()):
            y = alto - 12 - i * 9.5
            d.add(Rect(50*mm, y, 6, 6, fillColor=PALETA[i % len(PALETA)], strokeColor=None))
            txt = k if len(k) <= 20 else k[:18] + "…"
            d.add(String(50*mm + 9, y + 0.6, f"{txt}  {round(v*100/tot)}%",
                         fontName="Helvetica", fontSize=7.3,
                         fillColor=colors.HexColor("#33475b")))
        return d

    def tarjetas(valores):
        """Fila de datos fuerza."""
        celdas, estilos = [], [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]
        for i, (val, txt) in enumerate(valores):
            celdas.append(Paragraph(
                f'<para align="center"><font size="17" color="#0182c7"><b>{val}</b></font><br/>'
                f'<font size="7.6" color="#5a6b7a">{txt.upper()}</font></para>', est_texto))
            estilos += [("BACKGROUND", (i, 0), (i, 0), SUAVE),
                        ("LINEBELOW", (i, 0), (i, 0), 2.2, AZUL)]
        t = Table([celdas], colWidths=[170*mm/len(valores)] * len(valores))
        t.setStyle(TableStyle(estilos))
        return t

    def tabla(cabeceras, filas, anchos):
        data = [[Paragraph(f"<b>{c}</b>", est_celda_b) for c in cabeceras]]
        for f in filas:
            data.append([Paragraph(str(c), est_celda) for c in f])
        t = Table(data, colWidths=anchos, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SUAVE]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe4ec")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    # ── Membrete y pie ────────────────────────────────────────────────────────
    dir_front = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))

    def logo(nombre, alto_mm):
        """Inserta el logo reescalado: los originales pesan varios MB."""
        ruta = os.path.join(dir_front, nombre)
        if not os.path.exists(ruta):
            return ""
        try:
            if nombre not in _logo_cache:
                from PIL import Image as PILImage
                im = PILImage.open(ruta).convert("RGBA")
                im.thumbnail((520, 150), PILImage.LANCZOS)
                fondo = PILImage.new("RGB", im.size, (255, 255, 255))
                fondo.paste(im, mask=im.split()[3])
                buf = io.BytesIO()
                fondo.save(buf, "PNG", optimize=True)
                _logo_cache[nombre] = buf.getvalue()
            datos = io.BytesIO(_logo_cache[nombre])
            img = Image(datos)
            escala = (alto_mm*mm) / img.imageHeight
            img.drawHeight = alto_mm*mm
            img.drawWidth = img.imageWidth * escala
            return img
        except Exception as e:
            print(f"⚠  Logo {nombre} no incrustado: {e}")
            return ""

    def decorar(canvas, doc):
        canvas.saveState()
        # Franja superior
        canvas.setFillColor(AZUL)
        canvas.rect(0, A4[1] - 6*mm, A4[0], 6*mm, stroke=0, fill=1)
        # Pie
        canvas.setFillColor(colors.HexColor("#8b98a5"))
        canvas.setFont("Helvetica", 7.2)
        canvas.drawString(20*mm, 11*mm,
                          "SICAR Áncash · Gerencia Regional de Recursos Naturales y Gestión del Medio Ambiente")
        canvas.drawRightString(A4[0] - 20*mm, 11*mm, f"Página {doc.page}")
        canvas.setStrokeColor(colors.HexColor("#dbe4ec"))
        canvas.setLineWidth(0.4)
        canvas.line(20*mm, 14.5*mm, A4[0] - 20*mm, 14.5*mm)
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4,
                          leftMargin=20*mm, rightMargin=20*mm,
                          topMargin=15*mm, bottomMargin=20*mm,
                          title=f"Reporte ambiental — {valor}",
                          author="GRRNGMA · Gobierno Regional de Áncash")
    marco = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="cuerpo")
    doc.addPageTemplates([PageTemplate(id="base", frames=[marco], onPage=decorar)])

    E = []   # elementos del documento

    # ── Encabezado institucional ──────────────────────────────────────────────
    izq, der = logo("logo_izquierdo.png", 14), logo("logo_derecho.png", 14)
    if izq or der:
        cab = Table([[izq, "", der]], colWidths=[55*mm, 60*mm, 55*mm])
        cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("ALIGN", (2, 0), (2, 0), "RIGHT")]))
        E += [cab, Spacer(1, 6)]

    E += [
        Paragraph("REPORTE AMBIENTAL TERRITORIAL", est_subtit),
        Spacer(1, 4),
        Paragraph(f"{etiqueta_ambito} de {valor}"
                  if ambito != "cuenca" else str(valor), est_titulo),
        Paragraph(f"Departamento de Áncash · Emitido el {hoy}", est_subtit),
        Spacer(1, 12),
    ]

    # ── Datos fuerza ──────────────────────────────────────────────────────────
    fuerza = [(_num(total), "registros ambientales"),
              (str(len(por_tipo)), "conjuntos de datos"),
              (str(len(entidades)), "entidades fuente")]
    if resumen_tema:
        fuerza.append((_num(resumen_tema[0][1]), f"de {resumen_tema[0][0].lower()}"))
    E += [tarjetas(fuerza), Spacer(1, 10)]

    # ── Resumen narrativo ─────────────────────────────────────────────────────
    frase_tema = ", ".join(f"{n.lower()} ({_num(v)})" for n, v, _ in resumen_tema[:4])
    referencia = {"distrito": f"el distrito de <b>{valor}</b>",
                  "provincia": f"la provincia de <b>{valor}</b>",
                  "cuenca": f"la unidad hidrográfica <b>{valor}</b>"}[ambito]
    E += [
        Paragraph("1. Resumen", est_seccion),
        Paragraph(
            f"El presente reporte consolida la información ambiental disponible en el visor SICAR "
            f"para {referencia}. Se han identificado <b>{_num(total)}</b> "
            f"registros georreferenciados, distribuidos en <b>{len(por_tipo)}</b> conjuntos de datos "
            f"generados por <b>{len(entidades)}</b> entidades del Estado. "
            + (f"Las temáticas con mayor presencia son: {frase_tema}." if frase_tema else ""),
            est_texto),
        Spacer(1, 3),
        Paragraph(
            "Este documento reúne el panorama ambiental completo del ámbito consultado. Para obtener "
            "el detalle registro por registro, utilice la descarga en formato CSV del visor.", est_nota),
        Spacer(1, 4),
    ]

    # ── Composición por dataset ───────────────────────────────────────────────
    datos_barras = {k: int(v) for k, v in por_tipo.head(10).items()}
    E += [
        Paragraph("2. Composición de la información disponible", est_seccion),
        Paragraph("Cantidad de registros por conjunto de datos, ordenados de mayor a menor.",
                  est_texto),
        Spacer(1, 5),
        barras(datos_barras),
        Spacer(1, 8),
    ]

    filas = [(t, _num(int(v)), ENTIDAD_POR_TIPO.get(norm_txt(t), "—"),
              f"{_pct(int(v), total)}%") for t, v in por_tipo.items()]
    E += [tabla(["Conjunto de datos", "Registros", "Entidad responsable", "%"],
                filas, [58*mm, 20*mm, 76*mm, 16*mm])]

    # ── Distribución territorial ──────────────────────────────────────────────
    if desg:
        E += [
            Paragraph(f"3. {titulo_desg}", est_seccion),
            barras(desg),
        ]

    # ── Perfil temático ───────────────────────────────────────────────────────
    if len(resumen_tema) > 1:
        E += [
            Paragraph("4. Perfil temático", est_seccion),
            Paragraph("Distribución de los registros según las cuatro temáticas ambientales "
                      "que organiza el visor.", est_texto),
            Spacer(1, 4),
            dona({n: v for n, v, _ in resumen_tema}),
        ]

    # ── Pasivos mineros por riesgo ────────────────────────────────────────────
    if riesgo_pam:
        criticos = riesgo_pam.get("Alto", 0) + riesgo_pam.get("Muy alto", 0)
        total_pam = sum(riesgo_pam.values())
        E += [
            Paragraph("5. Pasivos ambientales mineros por nivel de riesgo", est_seccion),
            Paragraph(
                f"De los <b>{_num(total_pam)}</b> pasivos ambientales mineros inventariados por el "
                f"MINEM en este ámbito, <b>{_num(criticos)}</b> presentan riesgo alto o muy alto, "
                f"equivalente al <b>{_pct(criticos, total_pam)}%</b>.", est_texto),
            Spacer(1, 5),
            barras({k: v for k, v in sorted(riesgo_pam.items(), key=lambda x: -x[1])}),
        ]

    # ── Fuentes y nota metodológica ───────────────────────────────────────────
    E += [
        Paragraph("Fuentes de la información", est_seccion),
        tabla(["Entidad generadora"], [(e,) for e in entidades], [170*mm]),
        Spacer(1, 8),
        Paragraph(
            "<b>Nota metodológica.</b> Las cifras corresponden a los registros cargados en el visor "
            "SICAR Áncash al momento de la emisión y no representan necesariamente el universo total "
            "de cada temática. La información procede de fuentes oficiales de las entidades citadas; "
            "el Gobierno Regional de Áncash la integra y publica sin alterar el dato de origen. "
            "La periodicidad de actualización depende de cada entidad generadora. "
            "Este reporte cubre todos los conjuntos de datos disponibles en el ámbito consultado, "
            "con independencia de los filtros que estuvieran activos en el visor.", est_nota),
    ]

    doc.build(E)
    buffer.seek(0)

    limpio = _ud.normalize("NFD", valor).encode("ascii", "ignore").decode()
    limpio = "_".join(limpio.split())
    nombre = f"Reporte_SICAR_{ambito}_{limpio}.pdf"
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

@app.get("/api/chat/preguntas")
def chat_preguntas(tipo:str="",cuenca:str="",provincia:str="",distrito:str=""):
    cols_req = ["Tipo_Dataset","Cuenca","Provincia","Distrito"]
    if df.empty or not all(c in df.columns for c in cols_req): return {}
    dff = df.copy()
    if tipo:      dff = dff[dff["Tipo_Dataset"].str.contains(tipo,case=False,na=False)]
    if cuenca:    dff = dff[dff["Cuenca"].str.contains(cuenca,case=False,na=False)]
    if provincia: dff = dff[dff["Provincia"].str.contains(provincia,case=False,na=False)]
    if distrito:  dff = dff[dff["Distrito"].str.contains(distrito,case=False,na=False)]
    if len(dff) == 0: return {}

    ctx = []
    if tipo:      ctx.append(tipo.split(",")[0].strip())
    if cuenca:    ctx.append(f"cuenca {cuenca.split(',')[0].strip()}")
    if provincia: ctx.append(f"provincia {provincia.split(',')[0].strip()}")
    if distrito:  ctx.append(f"distrito {distrito.split(',')[0].strip()}")
    cs = " en ".join(ctx) if ctx else "en Áncash"

    p = {"Conteos": [(f"¿Cuántos registros hay {cs}?","count_total")]}
    if dff["Tipo_Dataset"].nunique() > 1:
        p["Conteos"].append((f"¿Cuántos tipos hay {cs}?","count_tipos"))
    ub = []
    if not provincia and dff["Provincia"].nunique() > 1:
        ub.append((f"¿Cuál es la provincia con más registros {cs}?","max_provincia"))
    if not cuenca and dff["Cuenca"].nunique() > 1:
        ub.append((f"¿Cuál es la cuenca con más puntos {cs}?","max_cuenca"))
    if ub: p["Ubicaciones"] = ub
    li = []
    if not cuenca    and dff["Cuenca"].nunique()>0:      li.append((f"¿Cuáles son las cuencas {cs}?","list_cuencas"))
    if not provincia and dff["Provincia"].nunique()>0:   li.append((f"¿Cuáles son las provincias {cs}?","list_provincias"))
    if not tipo      and dff["Tipo_Dataset"].nunique()>0:li.append((f"¿Qué tipos de datos hay {cs}?","list_tipos"))
    if li: p["Listados"] = li
    ag = []
    vc = "Volumen de derecho (m3)"
    if vc in dff.columns:
        dff[vc] = pd.to_numeric(dff[vc],errors='coerce')
        if dff[vc].notna().any():
            ag.append((f"¿Cuál es el volumen total {cs}?","sum_volumen"))
    if "Fuente Natural" in dff.columns and dff["Fuente Natural"].nunique()>0:
        ag.append((f"¿Cuáles son los ríos principales {cs}?","list_rios"))
    if ag: p["Agua"] = ag
    if "Tipo Uso" in dff.columns:
        us = []
        if dff["Tipo Uso"].str.contains("AGRÍCOLA",case=False,na=False).any():
            us.append((f"¿Cuántos derechos agrícolas hay {cs}?","count_agricola"))
        if dff["Tipo Uso"].str.contains("POBLACIONAL",case=False,na=False).any():
            us.append((f"¿Cuántos derechos poblacionales hay {cs}?","count_poblacional"))
        if us: p["Tipos de Uso"] = us
    return p

@app.post("/api/chat")
def chat(c: Consulta):
    partes = c.pregunta.split("|||")
    preg = partes[0]
    tipo = partes[1].strip() if len(partes)>1 else ""
    cuenca = partes[2].strip() if len(partes)>2 else ""
    prov = partes[3].strip() if len(partes)>3 else ""
    dist = partes[4].strip() if len(partes)>4 else ""
    dff = df.copy()
    if tipo:  dff = dff[dff["Tipo_Dataset"].str.contains(tipo,case=False,na=False)]
    if cuenca:dff = dff[dff["Cuenca"].str.contains(cuenca,case=False,na=False)]
    if prov:  dff = dff[dff["Provincia"].str.contains(prov,case=False,na=False)]
    if dist:  dff = dff[dff["Distrito"].str.contains(dist,case=False,na=False)]
    try:
        if "registros hay"     in preg: return {"respuesta":f"Hay <strong>{len(dff)}</strong> registros."}
        if "tipos hay"         in preg: return {"respuesta":f"Hay <strong>{dff['Tipo_Dataset'].nunique()}</strong> tipos."}
        if "provincia con más" in preg:
            v=dff["Provincia"].value_counts(); return {"respuesta":f"<strong>{v.idxmax()}</strong> ({v.max()} puntos)."}
        if "cuenca con más"    in preg:
            v=dff["Cuenca"].value_counts(); return {"respuesta":f"<strong>{v.idxmax()}</strong> ({v.max()} registros)."}
        if "cuencas"           in preg:
            return {"respuesta":"<strong>Cuencas:</strong><br>"+", ".join(sorted([x for x in dff["Cuenca"].unique() if x]))}
        if "provincias"        in preg:
            return {"respuesta":"<strong>Provincias:</strong><br>"+", ".join(sorted([x for x in dff["Provincia"].unique() if x]))}
        if "tipos de datos"    in preg:
            return {"respuesta":"<strong>Tipos:</strong><br>"+"<br>".join([f"• {t}" for t in sorted([x for x in dff["Tipo_Dataset"].unique() if x])])}
        vc = "Volumen de derecho (m3)"
        if "volumen total" in preg and vc in dff.columns:
            return {"respuesta":f"Volumen total: <strong>{pd.to_numeric(dff[vc],errors='coerce').sum():,.0f} m³</strong>."}
        if ("ríos" in preg or "fuentes" in preg) and "Fuente Natural" in dff.columns:
            rios=dff["Fuente Natural"].value_counts().head(10)
            return {"respuesta":"<strong>Fuentes:</strong><br>"+"<br>".join([f"• {r}: {cnt}" for r,cnt in rios.items()])}
        return {"respuesta":"Pregunta no reconocida. Usa las preguntas sugeridas."}
    except Exception as e:
        return {"respuesta":f"Error: {str(e)}"}