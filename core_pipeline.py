from pipelines.core_pipeline import CorePipeline

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("book_path")
    parser.add_argument("--output-root")
    args = parser.parse_args()
    CorePipeline().run(args.book_path, args.output_root)
