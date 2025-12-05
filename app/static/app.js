const fileInput = document.getElementById('fileInput');
const fileNameDisplay = document.getElementById('fileName');
const uploadBtn = document.getElementById('uploadBtn');
const uploadLoader = document.getElementById('uploadLoader');
const resultsSection = document.getElementById('resultsSection');
const citationsTableBody = document.querySelector('#citationsTable tbody');
const researchAllBtn = document.getElementById('researchAllBtn');
const modal = document.getElementById('resultModal');
const modalTitle = document.getElementById('modalTitle');
const modalBody = document.getElementById('modalBody');
const modalLoader = document.getElementById('modalLoader');
const closeBtn = document.querySelector('.close');

let currentCitations = [];

// File Selection
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        fileNameDisplay.textContent = e.target.files[0].name;
        uploadBtn.disabled = false;
    } else {
        fileNameDisplay.textContent = 'No file selected';
        uploadBtn.disabled = true;
    }
});

// Upload Handler
uploadBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    uploadLoader.style.display = 'block';
    uploadBtn.disabled = true;
    resultsSection.style.display = 'none';

    try {
        const response = await fetch('/analyze/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Upload failed');

        const data = await response.json();
        currentCitations = data.detected_citations;
        renderTable(currentCitations);
        resultsSection.style.display = 'block';
    } catch (error) {
        alert('Error uploading file: ' + error.message);
    } finally {
        uploadLoader.style.display = 'none';
        uploadBtn.disabled = false;
    }
});

// Render Table
function renderTable(citations) {
    citationsTableBody.innerHTML = '';
    citations.forEach(citation => {
        const row = document.createElement('tr');

        // Citation Cell
        const citeCell = document.createElement('td');
        citeCell.textContent = citation;
        row.appendChild(citeCell);

        // Actions Cell
        const actionsCell = document.createElement('td');
        actionsCell.className = 'actions';

        const validityBtn = document.createElement('button');
        validityBtn.className = 'btn btn-small';
        validityBtn.textContent = 'Check Validity';
        validityBtn.onclick = () => checkValidity(citation);

        const similarBtn = document.createElement('button');
        similarBtn.className = 'btn btn-small';
        similarBtn.textContent = 'Find Similar';
        similarBtn.onclick = () => findSimilar(citation);

        actionsCell.appendChild(validityBtn);
        actionsCell.appendChild(similarBtn);
        row.appendChild(actionsCell);

        // Status Cell (Placeholder)
        const statusCell = document.createElement('td');
        statusCell.id = `status-${citation.replace(/\s/g, '-')}`; // Simple ID sanitization
        row.appendChild(statusCell);

        citationsTableBody.appendChild(row);
    });
}

// Check Validity
async function checkValidity(citation) {
    openModal(`Validity Analysis: ${citation}`);
    try {
        const response = await fetch('/herding/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ citation: citation })
        });

        const data = await response.json();

        if (data.result) {
            const res = data.result;
            let html = `
                <div style="margin-bottom: 1rem;">
                    <strong>Is Good Law:</strong>
                    <span class="status-badge ${res.is_good_law ? 'status-good' : 'status-bad'}">
                        ${res.is_good_law ? 'YES' : 'NO'}
                    </span>
                    <span style="margin-left: 10px;">Confidence: ${Math.round(res.confidence * 100)}%</span>
                </div>
                <p><strong>Summary:</strong> ${res.summary}</p>
                <h3>Treatment Details</h3>
                <ul>
                    <li>Positive: ${res.positive_count}</li>
                    <li>Negative: ${res.negative_count}</li>
                    <li>Neutral: ${res.neutral_count}</li>
                </ul>
            `;

            if (res.warnings && res.warnings.length > 0) {
                 html += `<h3>Warnings</h3><ul>${res.warnings.map(w => `<li>${w.excerpt || w}</li>`).join('')}</ul>`;
            }

            modalBody.innerHTML = html;

            // Update status in table
            const statusCell = document.getElementById(`status-${citation.replace(/\s/g, '-')}`);
            if (statusCell) {
                statusCell.innerHTML = `<span class="status-badge ${res.is_good_law ? 'status-good' : 'status-bad'}">${res.is_good_law ? 'Good Law' : 'Flagged'}</span>`;
            }

        } else {
            modalBody.textContent = 'No results found.';
        }

    } catch (error) {
        modalBody.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
    } finally {
        modalLoader.style.display = 'none';
    }
}

// Find Similar
async function findSimilar(citation) {
    openModal(`Similar Cases: ${citation}`);
    try {
        const response = await fetch('/search/similar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: citation, limit: 5 })
        });

        const data = await response.json();

        if (data.results && data.results.length > 0) {
            const list = data.results.map(r => `
                <div style="border-bottom: 1px solid #eee; padding: 10px 0;">
                    <strong>${r.case_name || 'Unknown Case'}</strong> (${r.citation || 'No cit'})<br>
                    <small>Score: ${Math.round(r.similarity_score * 100)}% | ${r.court || 'Unknown Court'} | ${r.date_filed || 'Unknown Date'}</small>
                </div>
            `).join('');
            modalBody.innerHTML = list;
        } else {
            modalBody.innerHTML = '<p>No similar cases found.</p>';
        }

    } catch (error) {
        modalBody.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
    } finally {
        modalLoader.style.display = 'none';
    }
}

// Research All
researchAllBtn.addEventListener('click', async () => {
    if (currentCitations.length === 0) return;

    openModal('Comprehensive Research Pipeline');
    modalBody.innerHTML = '<p>Running deep research on all citations. This may take a while...</p>';

    try {
        const response = await fetch('/research/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                citations: currentCitations,
                key_questions: ["What is the primary holding?", "Is this case still good law?"]
            })
        });

        const data = await response.json();

        if (data.summary_markdown) {
            modalBody.innerHTML = marked.parse(data.summary_markdown);
        } else {
            modalBody.textContent = 'No summary generated.';
        }

    } catch (error) {
        modalBody.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
    } finally {
        modalLoader.style.display = 'none';
    }
});

// Modal Logic
function openModal(title) {
    modalTitle.textContent = title;
    modalBody.innerHTML = '';
    modalLoader.style.display = 'block';
    modal.style.display = 'block';
}

closeBtn.onclick = () => modal.style.display = 'none';
window.onclick = (e) => {
    if (e.target == modal) modal.style.display = 'none';
}
