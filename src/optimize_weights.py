"""CLI to optimize edge scoring weights using cached run data."""
import argparse
import logging

from src.optimization import WeightOptimizer, load_run_data

DEFAULT_FEATURES = ["is_ntlm", "source_fan_out", "dst_in_degree", "is_network_logon", "dst_fan_out_ratio"]

def main():
    parser = argparse.ArgumentParser(description="Optimize edge scoring weights using Nelder-Mead")
    parser.add_argument("--run-dir", required=True, help="Path to results run directory (e.g., results/20260504_183345)")
    parser.add_argument("--features", nargs="+", default=DEFAULT_FEATURES, help="Feature names to optimize (default: top-5)")
    parser.add_argument("--output-dir", default=None, help="Output directory for optimization files (default: <run-dir>/optimization)")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    features_df, labels = load_run_data(args.run_dir)

    output_dir = args.output_dir or f"{args.run_dir}/optimization"
    opt = WeightOptimizer(features_df, labels, args.features)
    result = opt.optimize(output_dir=output_dir)
    
    # Print results table
    print("\n" + "=" * 60)
    print("OPTIMIZATION RESULTS")
    print("=" * 60)
    print("  Method:      Nelder-Mead")
    print(f"  Iterations:  {result['iterations']}")
    print(f"  Converged:   {result['converged']}")
    print(f"  Time:        {result['total_time_seconds']:.2f}s")
    print(f"  Best AUC:    {result['auc']:.6f}")
    print("\n  Optimal weights:")
    for feat in args.features:
        print(f"    {feat:25s}: {result[feat]:.6f}")
    print("=" * 60)
    
    return result

if __name__ == "__main__":
    main()