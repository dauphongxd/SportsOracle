document.addEventListener('DOMContentLoaded', () => {
    const homeInput = document.getElementById('home-team');
    const awayInput = document.getElementById('away-team');
    const predictBtn = document.getElementById('predict-btn');
    const spinner = document.getElementById('loading-spinner');
    const btnText = document.getElementById('btn-text');
    const resultCard = document.getElementById('result-card');
    const errorMsg = document.getElementById('error-msg');

    // Autocomplete Logic
    setupAutocomplete(homeInput, 'home-suggestions');
    setupAutocomplete(awayInput, 'away-suggestions');

    // Load History
    loadHistory();

    // Predict Button Logic
    predictBtn.addEventListener('click', async () => {
        const homeTeam = homeInput.value;
        const awayTeam = awayInput.value;

        if (!homeTeam || !awayTeam) {
            showError("Please select both teams.");
            return;
        }

        setLoading(true);
        hideError();
        resultCard.style.display = 'none';

        try {
            const response = await fetch('/api/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ home_team: homeTeam, away_team: awayTeam })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Prediction failed");
            }

            displayPrediction(data);
            loadHistory(); // Refresh history
        } catch (err) {
            showError(err.message);
        } finally {
            setLoading(false);
        }
    });

    async function loadHistory() {
        const grid = document.getElementById('history-grid');
        try {
            const res = await fetch('/api/predictions');
            const predictions = await res.json();

            grid.innerHTML = '';
            if (predictions.length === 0) {
                grid.innerHTML = '<p style="color: var(--text-secondary)">No evaluations yet.</p>';
                return;
            }

            predictions.reverse().forEach(p => {
                const card = document.createElement('div');
                card.className = 'history-card';
                card.innerHTML = `
                    <span class="h-date">${p.date}</span>
                    <div class="h-matchup">
                        <div class="h-team">
                            ${p.home_logo ? `<img src="${p.home_logo}" class="team-logo-small">` : ''}
                            ${p.home_team}
                        </div>
                        <span class="h-vs">vs</span>
                        <div class="h-team">
                            ${p.away_team}
                            ${p.away_logo ? `<img src="${p.away_logo}" class="team-logo-small">` : ''}
                        </div>
                    </div>
                    <div class="h-prediction">
                        <div class="h-pred-label">AI Recommendation</div>
                        <div class="h-pred-val">${p.betting_advice.split('.')[0]}...</div>
                        <div style="margin-top: 0.5rem; display: flex; justify-content: space-between; align-items: center;">
                            <span class="risk-badge ${getRiskClass(p.risk_rating)}" style="font-size: 0.7rem; padding: 0.1rem 0.5rem;">Risk: ${p.risk_rating}/10</span>
                            <span style="font-size: 0.75rem; color: var(--text-secondary)">Conf: ${(p.confidence * 100).toFixed(0)}%</span>
                        </div>
                    </div>
                `;
                card.addEventListener('click', () => {
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                    // NOTE: History items won't have the full manager/context data
                    // unless we add them to the database, but for now we just show the result
                    displayPrediction(p);
                });
                grid.appendChild(card);
            });
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }

    function getRiskClass(rating) {
        if (rating <= 3) return 'risk-low';
        if (rating <= 6) return 'risk-medium';
        return 'risk-high';
    }

    function setupAutocomplete(input, listId) {
        const list = document.getElementById(listId);
        let debounceTimer;

        input.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            const query = input.value;

            if (query.length < 2) {
                list.classList.remove('active');
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/teams/search?q=${encodeURIComponent(query)}`);
                    const teams = await res.json();

                    list.innerHTML = '';
                    if (teams.length > 0) {
                        teams.forEach(team => {
                            const item = document.createElement('div');
                            item.className = 'suggestion-item';
                            item.innerHTML = `
                                ${team.logo_url ? `<img src="${team.logo_url}" class="team-logo-small">` : ''}
                                <span>${team.name}</span>
                            `;
                            item.addEventListener('click', () => {
                                input.value = team.name;
                                list.classList.remove('active');
                            });
                            list.appendChild(item);
                        });
                        list.classList.add('active');
                    } else {
                        list.classList.remove('active');
                    }
                } catch (e) {
                    console.error(e);
                }
            }, 300);
        });

        // Close suggestions on click outside
        document.addEventListener('click', (e) => {
            if (e.target !== input && e.target !== list) {
                list.classList.remove('active');
            }
        });
    }

    function displayPrediction(data) {
        // Update Header
        document.getElementById('home-name').textContent = data.home_team;
        document.getElementById('home-formation').textContent = data.home_formation || "Unknown";
        document.getElementById('away-formation').textContent = data.away_formation || "Unknown";

        document.getElementById('home-key-player').textContent = data.home_key_players || "No data";
        document.getElementById('away-key-player').textContent = data.away_key_players || "No data";

        if (data.home_deep_stats) {
            const h = data.home_deep_stats;
            document.getElementById('home-discipline').textContent =
                `${h.total_yellow_cards} Yellows, ${h.total_red_cards} Reds`;
        } else {
             document.getElementById('home-discipline').textContent = "No stats";
        }

        if (data.away_deep_stats) {
            const a = data.away_deep_stats;
            document.getElementById('away-discipline').textContent =
                `${a.total_yellow_cards} Yellows, ${a.total_red_cards} Reds`;
        } else {
             document.getElementById('away-discipline').textContent = "No stats";
        }

        document.getElementById('away-name').textContent = data.away_team;
        if (data.home_logo) document.getElementById('home-logo').src = data.home_logo;
        if (data.away_logo) document.getElementById('away-logo').src = data.away_logo;

        // NEW: Update Context & Managers
        const derbyEl = document.getElementById('derby-alert');
        if (data.derby_alert) {
            derbyEl.textContent = data.derby_alert;
            derbyEl.style.display = 'block';
        } else {
            derbyEl.style.display = 'none';
        }

        // Only update if data exists (history items might not have this)
        if(data.home_manager) {
            document.getElementById('home-manager').textContent = data.home_manager;
            document.getElementById('away-manager').textContent = data.away_manager;
            document.getElementById('home-stakes').textContent = data.home_context || '';
            document.getElementById('away-stakes').textContent = data.away_context || '';
        }

        // Update Stats Bars
        updateStat('home-win', data.home_win_probability, data.home_team);
        updateStat('draw', data.draw_probability, 'Draw');
        updateStat('away-win', data.away_win_probability, data.away_team);

        // Update Risk
        const riskEl = document.getElementById('risk-badge');
        riskEl.textContent = `Risk Rating: ${data.risk_rating}/10`;
        riskEl.className = 'risk-badge ' + (
            data.risk_rating <= 3 ? 'risk-low' :
                data.risk_rating <= 6 ? 'risk-medium' : 'risk-high'
        );

        // Update Advice
        document.getElementById('advice-text').innerHTML = data.betting_advice.replace(/\n/g, '<br>');

        // Update Reasoning
        document.getElementById('reasoning-text').innerHTML = (data.reasoning || "No detailed analysis available.").replace(/\n/g, '<br>');

        // Update Buttons
        updateBetBtn('btn-home', data.odds?.home_win, 'HOME_WIN', data.match_id);
        updateBetBtn('btn-draw', data.odds?.draw, 'DRAW', data.match_id);
        updateBetBtn('btn-away', data.odds?.away_win, 'AWAY_WIN', data.match_id);

        resultCard.style.display = 'block';
    }

    function updateStat(idPrefix, prob, label) {
        const percentage = (prob * 100).toFixed(0) + '%';
        document.getElementById(`${idPrefix}-label`).textContent = label;
        document.getElementById(`${idPrefix}-val`).textContent = percentage;
        document.getElementById(`${idPrefix}-bar`).style.width = percentage;
    }

    function updateBetBtn(btnId, odds, betType, matchId) {
        const btn = document.getElementById(btnId);
        const oddsSpan = btn.querySelector('.bet-odds');

        if (odds) {
            oddsSpan.textContent = odds.toFixed(2);
            btn.disabled = false;
            btn.onclick = () => placeBet(matchId, betType, odds);
        } else {
            oddsSpan.textContent = '-';
            btn.disabled = true;
        }
    }

    async function placeBet(matchId, betType, odds) {
        if (!confirm(`Place bet on ${betType} @ ${odds}?`)) return;

        try {
            const res = await fetch('/api/bets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    match_id: matchId,
                    bet_type: betType,
                    stake_amount: 100,
                    odds: odds
                })
            });

            if (res.ok) {
                alert('✅ Bet placed successfully!');
            } else {
                alert('❌ Failed to place bet');
            }
        } catch (e) {
            alert('Error placing bet');
        }
    }

    function setLoading(isLoading) {
        predictBtn.disabled = isLoading;
        spinner.style.display = isLoading ? 'block' : 'none';
        btnText.style.display = isLoading ? 'none' : 'block';
    }

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.style.display = 'block';
        errorMsg.style.color = 'var(--danger-color)';
        errorMsg.style.marginTop = '1rem';
        errorMsg.style.textAlign = 'center';
    }

    function hideError() {
        errorMsg.style.display = 'none';
    }
});