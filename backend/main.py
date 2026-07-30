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
import json, os, glob

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

# Filtrar puntos que caen dentro del área de cuencas
try:
    import geopandas as gpd
    from shapely.geometry import Point

    ruta_cuencas = os.path.join(BASE_DIR, "limite_cuencas.geojson")
    gdf_cuencas = gpd.read_file(ruta_cuencas)
    if gdf_cuencas.crs and gdf_cuencas.crs.to_epsg() != 4326:
        gdf_cuencas = gdf_cuencas.to_crs("EPSG:4326")

    # Union de todos los polígonos → área total de interés
    area_total = gdf_cuencas.union_all()

    # Filtrar solo filas con coordenadas válidas dentro del área
    lat_col = next((c for c in ["Latitud","Y"] if c in df.columns), None)
    lon_col = next((c for c in ["Longitud","X"] if c in df.columns), None)

    if lat_col and lon_col:
        df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
        df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
        df_val = df.dropna(subset=[lat_col, lon_col])
        gdf_pts = gpd.GeoDataFrame(
            df_val,
            geometry=gpd.points_from_xy(df_val[lon_col], df_val[lat_col]),
            crs="EPSG:4326"
        )
        joined = gpd.sjoin(gdf_pts, gdf_cuencas[["geometry"]],
                           how="inner", predicate="within")
        antes = len(df)
        df = df.loc[joined.index.unique()].copy()
        print(f"✅ Filtro espacial: {antes} → {len(df)} puntos dentro del área de cuencas")
except Exception as e:
    print(f"⚠  Filtro espacial no aplicado: {e}")

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

@app.get("/api/filtros")
def get_filtros():
    return {"tipos": _uniq("Tipo_Dataset"), "cuencas": _uniq("Cuenca"),
            "provincias": _uniq("Provincia"), "distritos": _uniq("Distrito")}

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

@app.post("/api/cascada")
def cascada(f: Filtros):
    dt = df.copy()
    if f.tipo:     dt = dt[dt["Tipo_Dataset"].str.upper().isin([t.upper() for t in f.tipo])]
    cu = sorted([x for x in dt["Cuenca"].unique()    if x]) if "Cuenca"    in dt.columns else []
    if f.cuenca:   dt = dt[dt["Cuenca"].str.upper().isin([c.upper() for c in f.cuenca])]
    pr = sorted([x for x in dt["Provincia"].unique() if x]) if "Provincia" in dt.columns else []
    if f.provincia:dt = dt[dt["Provincia"].str.upper().isin([p.upper() for p in f.provincia])]
    di = sorted([x for x in dt["Distrito"].unique()  if x]) if "Distrito"  in dt.columns else []
    return {"cuencas": cu, "provincias": pr, "distritos": di}

@app.post("/api/filtrar")
def filtrar(f: Filtros):
    dff = df.copy()
    if f.tipo:      dff = dff[dff["Tipo_Dataset"].str.upper().isin([t.upper() for t in f.tipo])]
    if f.cuenca:    dff = dff[dff["Cuenca"].str.upper().isin([c.upper() for c in f.cuenca])]
    if f.provincia: dff = dff[dff["Provincia"].str.upper().isin([p.upper() for p in f.provincia])]
    if f.distrito:  dff = dff[dff["Distrito"].str.upper().isin([d.upper() for d in f.distrito])]

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

@app.get("/api/poligonos/ancash")     
def g_ancash():    return gjson("limite_ancash.geojson")
@app.get("/api/poligonos/cuencas")    
def g_cuencas():   return gjson("limite_cuencas.geojson")
@app.get("/api/poligonos/provincias") 
def g_prov():      return gjson("limite_provincias.geojson")
@app.get("/api/poligonos/distritos")  
def g_dist():      return gjson("limite_distritos.geojson")

@app.get("/api/poligonos/subcuencas")
def g_subcuencas(cuencas: str = "", nombres: str = "", solo_nombres: int = 0):
    """
    Tres modos de uso:
      - ?cuencas=Cuenca+Santa,...&solo_nombres=1  → devuelve {"nombres": [...]} para poblar el dropdown
      - ?cuencas=Cuenca+Santa,...                 → GeoJSON de subcuencas que intersectan esas cuencas
      - ?nombres=Alto+Santa,Medio+Casma,...       → GeoJSON de subcuencas con esos nombres exactos
    """
    try:
        import geopandas as gpd
        from shapely.ops import unary_union

        gdf_sub = gpd.read_file(os.path.join(BASE_DIR, "limite_subcuencas.geojson"))
        if gdf_sub.crs and gdf_sub.crs.to_epsg() != 4326:
            gdf_sub = gdf_sub.to_crs("EPSG:4326")

        COL_NOMBRE = next(
            (c for c in ["Nombre_UH", "NOMBRE", "Nombre", "nombre"] if c in gdf_sub.columns),
            None
        )

        # ── Modo A: filtrar por cuencas padre (intersección espacial) ──
        if cuencas.strip():
            nombres_cuenca = [c.strip() for c in cuencas.split(",") if c.strip()]
            ruta_cuencas = os.path.join(BASE_DIR, "limite_cuencas.geojson")
            gdf_cuencas = gpd.read_file(ruta_cuencas)
            if gdf_cuencas.crs and gdf_cuencas.crs.to_epsg() != 4326:
                gdf_cuencas = gdf_cuencas.to_crs("EPSG:4326")

            col_nombre_cuenca = next(
                (c for c in ["NOMBRE", "Nombre", "nombre", "CUENCA", "Cuenca"]
                 if c in gdf_cuencas.columns), None
            )
            if col_nombre_cuenca:
                mask = gdf_cuencas[col_nombre_cuenca].str.upper().isin(
                    [n.upper() for n in nombres_cuenca]
                )
                seleccionadas = gdf_cuencas[mask]
            else:
                seleccionadas = gdf_cuencas

            if not seleccionadas.empty:
                area_union = unary_union(seleccionadas.geometry)
                gdf_sub = gdf_sub[gdf_sub.geometry.intersects(area_union)]

            # Modo A + solo_nombres: devolver lista de nombres para el dropdown
            if solo_nombres:
                if COL_NOMBRE:
                    lista = sorted([
                        str(v) for v in gdf_sub[COL_NOMBRE].dropna().unique() if str(v).strip()
                    ])
                else:
                    lista = []
                return {"nombres": lista}

            return json.loads(gdf_sub.to_json())

        # ── Modo B: filtrar por nombres explícitos de subcuencas ──
        if nombres.strip():
            lista_nombres = [n.strip() for n in nombres.split(",") if n.strip()]
            if COL_NOMBRE:
                gdf_sub = gdf_sub[
                    gdf_sub[COL_NOMBRE].str.strip().isin(lista_nombres)
                ]
            return json.loads(gdf_sub.to_json())

        # Sin parámetros: devolver todas
        return json.loads(gdf_sub.to_json())

    except Exception as e:
        print(f"⚠  Subcuencas: {e}")
        return gjson("limite_subcuencas.geojson")
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