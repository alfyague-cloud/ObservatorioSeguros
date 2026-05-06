# Observatorio Seguros

Análisis comparado de aseguradoras españolas a partir del **Libro de Balances y Cuentas** de la DGSFP. Vista 360º de balance, cuenta de pérdidas y ganancias, solvencia y plantilla, con comparativas entre entidades y agregados sectoriales.

## Demo

Una vez desplegado en GitHub Pages, accesible en `https://USUARIO.github.io/REPO/`.

## Características

- **241 entidades** aseguradoras desde 2016 hasta 2024.
- **Vista 360º**: Resumen, Balance, PyG, Solvencia, Plantilla, Evolución temporal.
- Comparación simultánea de hasta **6 entidades** con código de color y sparklines de tendencia.
- **Agregados sectoriales** como entidades virtuales: SECTOR (todas), Sociedades anónimas, Mutuas, Mutualidades. Los ratios CSO/CMO se recalculan correctamente como `Σ FP / Σ Capital`.
- **Constructor de ratios personalizados** en Evolución: cualquier partida (de balance, PyG o solvencia) ÷ ó × cualquier otra, opcional ×100 para porcentaje.
- Indicadores delta YoY, gauges SVG, gráficos Chart.js.
- Logo Afi via CDN.

## Stack

Sin frameworks de build. Una sola página HTML con JS vanilla y Chart.js desde CDN. Datos preprocesados en Python a un único `dgsfp.json`.

## Estructura

```
observatorio-seguros/
├── index.html                  # Aplicación web (todo el código UI)
├── data/
│   ├── dgsfp.json              # Dataset preprocesado (generado por scripts/build.py)
│   └── raw/                    # CSVs originales de la DGSFP
│       ├── D0101t.csv          # identificación
│       ├── D0301T.csv ...      # balance, PyG, solvencia
│       ├── L0301t.csv ...      # literales (descripciones de PT)
│       ├── Provincias.csv, Paises.csv, Aux*.csv
│       └── ayuda_para_la_consulta_de_tablas_a_partir_2016.pdf
├── scripts/
│   └── build.py                # Preprocesador: CSV → dgsfp.json
├── .github/workflows/
│   └── deploy.yml              # Auto-deploy a GitHub Pages
├── README.md
├── LICENSE
└── .gitignore
```

## Cómo ejecutar localmente

Necesitas un servidor HTTP (la web hace `fetch('./data/dgsfp.json')`, no funciona con `file://`):

```bash
# Python
python3 -m http.server 8000

# Node
npx serve .
```

Abre `http://localhost:8000`.

## Cómo desplegar en GitHub Pages

1. Crea un repo en GitHub y sube el contenido:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin git@github.com:USUARIO/REPO.git
   git push -u origin main
   ```
2. En el repo: **Settings → Pages → Source → GitHub Actions**.
3. El workflow `.github/workflows/deploy.yml` publica automáticamente en cada push a `main`.

A los pocos segundos la web está en `https://USUARIO.github.io/REPO/`.

## Cómo actualizar los datos cuando la DGSFP publique nuevo ejercicio

1. Sustituye los CSV en `data/raw/` por los del nuevo ejercicio (manteniendo nombres).
2. Regenera el dataset:
   ```bash
   python3 scripts/build.py
   ```
3. Commit y push:
   ```bash
   git add data/
   git commit -m "Datos actualizados <ejercicio>"
   git push
   ```

GitHub Pages se redespliega solo.

## Personalizar la apariencia

Casi toda la apariencia vive en variables CSS al inicio de `index.html`:

```css
:root {
  --primary: #0a2a52;   /* navy Afi */
  --accent:  #0891b2;   /* teal */
  --gold:    #d97706;   /* highlights / agregados */
  ...
}
```

Cambia los hex y se aplica a toda la app.

## Fuente y derechos sobre los datos

Datos públicos de la **Dirección General de Seguros y Fondos de Pensiones** (DGSFP) — Libro de Balances y Cuentas. Documentación oficial en `data/raw/ayuda_para_la_consulta_de_tablas_a_partir_2016.pdf`.

## Licencia

Apache License 2.0 — ver [LICENSE](./LICENSE) y [NOTICE](./NOTICE).

Antes de hacer público el repo, edita `NOTICE` y pon el titular del copyright (Afi, tu nombre, etc.).
