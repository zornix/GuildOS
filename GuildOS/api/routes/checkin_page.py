from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.services.checkin_links import validate_checkin_link
from api.config import settings

router = APIRouter()


@router.get("/{short_code}", response_class=HTMLResponse)
async def checkin_page(short_code: str):
    """
    GET /c/A7x9Kp -> serves a lightweight HTML check-in page.

    Members enter their 9-digit phone number to check in.
    No Supabase session or JWT required.
    """
    link_data = await validate_checkin_link(short_code)

    if not link_data:
        return HTMLResponse(
            content="<h1>Link expired</h1><p>This check-in link is no longer valid.</p>",
            status_code=410,
        )

    event = link_data["events"]

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Check In — {event['title']}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #0f0f1a; color: #e2e8f0; display: flex;
                    align-items: center; justify-content: center;
                    min-height: 100vh; padding: 20px; }}
            .card {{ background: #1a1a2e; border-radius: 16px; padding: 32px;
                     max-width: 400px; width: 100%; text-align: center;
                     border: 1px solid #2a2a45; }}
            h1 {{ font-size: 20px; margin-bottom: 4px; }}
            .sub {{ color: #94a3b8; font-size: 14px; margin-bottom: 24px; }}
            .phone-input {{ width: 100%; padding: 14px 16px; border-radius: 10px;
                           border: 1px solid #2a2a45; background: #0f0f1a;
                           color: #e2e8f0; font-size: 22px; text-align: center;
                           letter-spacing: 2px; font-weight: 600;
                           margin-bottom: 16px; outline: none;
                           transition: border-color 0.2s; }}
            .phone-input:focus {{ border-color: #6c5ce7; }}
            .phone-input::placeholder {{ color: #4a4a6a; font-weight: 400;
                                        letter-spacing: 1px; font-size: 16px; }}
            .btn {{ display: block; width: 100%; padding: 14px; border-radius: 10px;
                    border: none; background: #6c5ce7; color: white; font-size: 15px;
                    font-weight: 700; cursor: pointer; transition: opacity 0.2s; }}
            .btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
            .btn:not(:disabled):hover {{ opacity: 0.9; }}
            .status {{ padding: 16px; border-radius: 12px; font-size: 15px;
                       font-weight: 600; margin-top: 16px; display: none; }}
            .success {{ background: #10b98122; color: #10b981; display: block; }}
            .error {{ background: #ef444422; color: #ef4444; display: block; }}
            .hint {{ color: #64748b; font-size: 12px; margin-top: 8px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>{event['title']}</h1>
            <p class="sub">{event['date']} &middot; {event['location']}</p>

            <form id="checkin-form">
                <input
                    id="phone"
                    class="phone-input"
                    type="tel"
                    inputmode="numeric"
                    maxlength="11"
                    placeholder="123-456-789"
                    autocomplete="off"
                    required
                />
                <button id="submit-btn" class="btn" type="submit" disabled>
                    Check In
                </button>
                <p class="hint">Enter your 9-digit phone number</p>
            </form>

            <div id="status" class="status"></div>
        </div>
        <script>
            const SHORT_CODE = '{short_code}';
            const API_BASE = '{settings.BASE_URL}';
            const phoneInput = document.getElementById('phone');
            const form = document.getElementById('checkin-form');
            const submitBtn = document.getElementById('submit-btn');
            const statusEl = document.getElementById('status');

            function formatPhone(raw) {{
                const d = raw.replace(/\\D/g, '').slice(0, 9);
                if (d.length <= 3) return d;
                if (d.length <= 6) return d.slice(0,3) + '-' + d.slice(3);
                return d.slice(0,3) + '-' + d.slice(3,6) + '-' + d.slice(6);
            }}

            function getDigits() {{
                return phoneInput.value.replace(/\\D/g, '');
            }}

            phoneInput.addEventListener('input', function() {{
                const pos = this.selectionStart;
                const before = this.value.length;
                this.value = formatPhone(this.value);
                const after = this.value.length;
                const newPos = pos + (after - before);
                this.setSelectionRange(newPos, newPos);
                submitBtn.disabled = getDigits().length !== 9;
            }});

            form.addEventListener('submit', async function(e) {{
                e.preventDefault();
                const digits = getDigits();
                if (digits.length !== 9) return;

                submitBtn.disabled = true;
                submitBtn.textContent = 'Checking in...';
                statusEl.className = 'status';
                statusEl.style.display = 'none';

                try {{
                    const res = await fetch(
                        API_BASE + '/api/attendance/checkin/' + SHORT_CODE + '/phone',
                        {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ phone: digits }}),
                        }}
                    );
                    const data = await res.json();

                    if (res.ok) {{
                        statusEl.className = 'status success';
                        statusEl.textContent = "You're checked in!";
                        form.style.display = 'none';
                    }} else {{
                        statusEl.className = 'status error';
                        statusEl.textContent = data.detail || 'Check-in failed';
                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Check In';
                    }}
                }} catch (err) {{
                    statusEl.className = 'status error';
                    statusEl.textContent = 'Network error. Try again.';
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Check In';
                }}
            }});

            phoneInput.focus();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
