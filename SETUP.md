# 🚀 Guía de Setup — CPG Price Intelligence
## Tiempo estimado: 45-60 minutos | Costo: $0 para empezar

---

## PASO 1 — Crear cuenta en GitHub (5 min)
**URL:** https://github.com/signup

1. Ve a github.com/signup
2. Usa tu email: samgzzgzz2@gmail.com
3. Elige un username (ej. `samgz-cpg`)
4. Verifica tu email

---

## PASO 2 — Crear el repositorio (3 min)
1. En GitHub, haz clic en el botón verde **"New"** (esquina superior izquierda)
2. Nombre del repo: `cpg-scraper`
3. Visibilidad: **Private** (para que nadie vea tus datos)
4. ✅ Marca "Add a README file"
5. Clic en **"Create repository"**

---

## PASO 3 — Subir el código (10 min)

### Opción A — Desde la web (sin instalar nada)
1. En tu repositorio recién creado, haz clic en **"uploading an existing file"**
2. Arrastra TODOS los archivos y carpetas de la carpeta `cpg-scraper/` que te entregué
3. Escribe en el campo de commit: `"Initial setup"`
4. Clic en **"Commit changes"**

### Opción B — Con Git (si tienes Git instalado)
```bash
cd cpg-scraper          # ir a la carpeta del código
git init
git remote add origin https://github.com/TU_USERNAME/cpg-scraper.git
git add .
git commit -m "Initial setup"
git push -u origin main
```

---

## PASO 4 — Crear cuenta en Supabase (5 min)
**URL:** https://supabase.com

1. Clic en **"Start your project"**
2. Inicia sesión con tu cuenta de GitHub (botón "Continue with GitHub") — más rápido
3. Clic en **"New Project"**
4. Nombre: `cpg-intel`
5. Región: **South America (São Paulo)** — la más cercana a México
6. Genera una contraseña fuerte (guárdala, aunque no la usaremos directamente)
7. Clic en **"Create new project"** y espera ~2 minutos

### Crear las tablas (SQL)
1. En el menú izquierdo de Supabase, clic en **"SQL Editor"**
2. Clic en **"New Query"**
3. Copia y pega el contenido completo del archivo `supabase_schema.sql`
4. Clic en **"Run"** (botón verde, o Ctrl+Enter)
5. Debes ver: `Success. No rows returned`

### Obtener tus credenciales de Supabase
1. En el menú izquierdo, clic en ⚙️ **"Project Settings"**
2. Clic en **"API"**
3. Anota (copia) estos dos valores:
   - **Project URL**: algo como `https://xxxxx.supabase.co`
   - **service_role key** (NO la anon key — desplázate hacia abajo para verla)

---

## PASO 5 — Crear cuenta en Twilio para WhatsApp (10 min)
**URL:** https://www.twilio.com/try-twilio

1. Regístrate con tu email
2. Verifica tu número de teléfono (el que usa WhatsApp)
3. Cuando pregunte "What are you building?": selecciona **"WhatsApp"**
4. Te dan **$15 USD de crédito gratis** — suficiente para meses de notificaciones

### Activar WhatsApp Sandbox
1. En el menú izquierdo: **Messaging → Try it out → Send a WhatsApp message**
2. Sigue las instrucciones: manda un WhatsApp al número `+1 415 523 8886` con el código que te dan (algo como `join word-word`)
3. Verás confirmación de que tu número está en el sandbox

### Obtener tus credenciales de Twilio
En el Dashboard principal de Twilio:
- **Account SID**: empieza con "AC..." — anótalo
- **Auth Token**: clic en "eye" para ver — anótalo
- **From number**: `+14155238886` (el sandbox de Twilio)
- **Your WhatsApp**: tu número en formato internacional, ej. `+5219991234567`

---

## PASO 6 — Configurar secrets en GitHub (5 min)
**Este es el paso más importante — aquí conectas todo.**

1. Ve a tu repositorio en GitHub
2. Clic en **"Settings"** (pestaña superior)
3. En el menú izquierdo: **"Secrets and variables"** → **"Actions"**
4. Clic en **"New repository secret"** y agrega estos 7 secrets:

| Nombre del Secret | Valor |
|---|---|
| `SUPABASE_URL` | La Project URL de Supabase (https://xxxxx.supabase.co) |
| `SUPABASE_KEY` | La service_role key de Supabase |
| `TWILIO_ACCOUNT_SID` | Tu Account SID de Twilio (empieza con "AC") |
| `TWILIO_AUTH_TOKEN` | Tu Auth Token de Twilio |
| `TWILIO_FROM` | `whatsapp:+14155238886` |
| `WHATSAPP_TO` | Tu número con código de país, ej. `+5219991234567` |
| `MELI_ACCESS_TOKEN` | (opcional por ahora, deja en blanco o pon `none`) |

---

## PASO 7 — Activar GitHub Pages (3 min)
El dashboard HTML se publicará aquí automáticamente.

1. En tu repositorio → **Settings**
2. Menú izquierdo: **Pages**
3. En "Source": selecciona **"Deploy from a branch"**
4. Branch: **`gh-pages`** | Folder: **`/ (root)`**
5. Clic en **Save**

> La primera vez, la rama `gh-pages` se crea automáticamente cuando corre el scraper.
> Tu URL del dashboard será: `https://TU_USERNAME.github.io/cpg-scraper/`

---

## PASO 8 — Primer run manual (2 min)
Para probar que todo funciona sin esperar a las 2 AM:

1. Ve a tu repositorio → pestaña **"Actions"**
2. En el menú izquierdo: **"📊 CPG Daily Price Scraper"**
3. Clic en **"Run workflow"** → **"Run workflow"** (botón verde)
4. Aparecerá un círculo naranja → espera 15-30 minutos
5. Si se pone ✅ verde: todo bien. Si se pone ❌ rojo: revisa los logs

### Ver los logs
Si algo falla, clic en el run → clic en el job **"Scrape & Update Dashboard"** → puedes ver qué pasó línea a línea.

---

## PASO 9 — Registrarse en MeLi Developers (10 min, opcional)
Esto mejora la calidad de datos de Mercado Libre.

1. Ve a: https://developers.mercadolibre.com.mx/
2. Crea una app con tu cuenta de MeLi
3. En los permisos, activa: `read_catalog`
4. Obtén tu **Access Token** (dura 6 horas — necesitarás configurar refresh, pero para empezar funciona el token inicial)
5. Agrégalo en GitHub como secret `MELI_ACCESS_TOKEN`

---

## ✅ Checklist Final

- [ ] Cuenta GitHub creada
- [ ] Repositorio `cpg-scraper` creado (privado)
- [ ] Código subido al repo
- [ ] Cuenta Supabase creada
- [ ] Tablas creadas con el SQL
- [ ] Cuenta Twilio creada
- [ ] WhatsApp sandbox activado (mensaje enviado a Twilio)
- [ ] Los 6 secrets configurados en GitHub
- [ ] GitHub Pages activado
- [ ] Primer run manual exitoso

---

## 🔧 Solución de Problemas Comunes

### "Module not found" en el run
→ Verifica que subiste TODOS los archivos y carpetas (incluyendo `scrapers/`, `core/`, `.github/`)

### "Invalid API key" en Supabase
→ Asegúrate de usar la **service_role** key, no la "anon" key

### No llega el WhatsApp
→ Confirma que enviaste el mensaje de join al sandbox. El formato del número debe ser con `+` y código de país.

### El scraper no encuentra precios (precio = null para todos)
→ Es normal que pase los primeros días — los selectores CSS pueden necesitar ajuste.
→ Ve a GitHub → Actions → el run fallido → descarga los logs → mándame los logs y lo ajustamos

### Walmart siempre da error
→ Normal sin proxies. El resto de cadenas sí funciona. Walmart lo agregamos cuando tengas presupuesto para proxies.

---

## 📅 ¿Cuándo corre automáticamente?
Todos los días a las **02:00 AM hora México (CDT)** = 08:00 UTC.
Recibirás WhatsApp con el resumen cada mañana antes de empezar tu día.

---

## 💰 Costos actuales: $0/mes
- GitHub: Gratis (repositorios privados incluidos)
- Supabase: Gratis (hasta 500 MB de datos ≈ 3-4 años de historial)
- GitHub Actions: Gratis (2,000 minutos/mes — el scraper usa ~25 min/día = 750/mes)
- Twilio WhatsApp Sandbox: $15 USD de crédito gratis (~$0.005/msg = 3,000 mensajes)

**Cuando crecer:**
- Si necesitas Amazon MX: agregar proxies Smartproxy ~$75 USD/mes
- Si superas 500 MB en Supabase: plan Pro $25 USD/mes
