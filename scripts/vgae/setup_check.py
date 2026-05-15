"""Phase-0 gate for the VGAE baseline.

Verifies the dedicated .venv-vgae has a working torch + PyG install on
this machine. Run with:
    .venv-vgae/bin/python scripts/vgae/setup_check.py

Checks:
  1. torch imports cleanly
  2. MPS is available (Apple Silicon GPU); falls back to CPU if not
  3. torch_geometric imports cleanly
  4. Build a tiny synthetic graph and run one VGAE forward + backward pass
  5. Confirm device transfer works

Exits 0 on success, 1 on failure. Failure mode is documented to stdout
so we can decide whether to proceed to Phase 1 or abort.
"""

from __future__ import annotations

import sys
import time


def main() -> int:
    print("=" * 70)
    print("VGAE setup check")
    print("=" * 70)
    print(f"Python: {sys.version.splitlines()[0]}")
    print(f"Executable: {sys.executable}")

    try:
        import torch
    except ImportError as e:
        print(f"FAIL torch import: {e}")
        return 1
    print(f"OK   torch {torch.__version__}")

    mps_available = torch.backends.mps.is_available()
    cuda_available = torch.cuda.is_available()
    if mps_available:
        device = torch.device("mps")
        print(f"OK   MPS available  -> device = {device}")
    elif cuda_available:
        device = torch.device("cuda")
        print(f"OK   CUDA available -> device = {device}")
    else:
        device = torch.device("cpu")
        print(f"WARN no GPU detected -> device = {device}")

    try:
        import torch_geometric
        from torch_geometric.nn import VGAE, GCNConv
    except ImportError as e:
        print(f"FAIL torch_geometric import: {e}")
        return 1
    print(f"OK   torch_geometric {torch_geometric.__version__}")

    print()
    print("Building synthetic graph (100 nodes, 500 edges, 16 features)")
    torch.manual_seed(0)
    n, num_edges, d_in, hidden, latent = 100, 500, 16, 32, 16
    x = torch.randn(n, d_in)
    edge_index = torch.randint(0, n, (2, num_edges))

    class Encoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = GCNConv(d_in, hidden)
            self.conv_mu = GCNConv(hidden, latent)
            self.conv_logstd = GCNConv(hidden, latent)

        def forward(self, x, edge_index):
            h = self.conv1(x, edge_index).relu()
            return self.conv_mu(h, edge_index), self.conv_logstd(h, edge_index)

    model = VGAE(Encoder()).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    x_dev = x.to(device)
    edge_dev = edge_index.to(device)

    print(f"Running 5 training steps on {device}...")
    t0 = time.time()
    try:
        for step in range(5):
            optimizer.zero_grad()
            z = model.encode(x_dev, edge_dev)
            loss = model.recon_loss(z, edge_dev) + (1.0 / n) * model.kl_loss()
            loss.backward()
            optimizer.step()
            print(f"  step {step + 1}: loss = {loss.item():.4f}")
    except Exception as e:
        print(f"FAIL forward/backward on {device}: {e}")
        if device.type == "mps":
            print("INFO retrying on CPU as fallback...")
            try:
                model = VGAE(Encoder()).to("cpu")
                optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
                for step in range(5):
                    optimizer.zero_grad()
                    z = model.encode(x, edge_index)
                    loss = model.recon_loss(z, edge_index) + (1.0 / n) * model.kl_loss()
                    loss.backward()
                    optimizer.step()
                print("OK   CPU fallback works; will use CPU for the real run")
                device = torch.device("cpu")
            except Exception as e2:
                print(f"FAIL CPU fallback also broke: {e2}")
                return 1
        else:
            return 1
    elapsed = time.time() - t0
    print(f"OK   5 training steps in {elapsed:.2f}s on {device}")

    print()
    print("=" * 70)
    print(f"GATE PASSED. Recommended device for VGAE run: {device}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
