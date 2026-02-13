const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("╔════════════════════════════════════════════════╗");
  console.log("║  DeepFake Detection - Smart Contract Deployer  ║");
  console.log("╚════════════════════════════════════════════════╝");
  console.log(`\nNetwork: ${hre.network.name}`);
  console.log(`Chain ID: ${hre.network.config.chainId || "N/A"}\n`);

  // Get deployer account
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deployer address:", deployer.address);

  // Check balance
  const balance = await deployer.provider.getBalance(deployer.address);
  const balanceEth = hre.ethers.formatEther(balance);
  console.log("Account balance:", balanceEth, "MATIC\n");

  if (parseFloat(balanceEth) < 0.01) {
    console.warn("⚠️  WARNING: Low balance. Deployment may fail.");
    console.warn("   Get testnet MATIC from: https://faucet.polygon.technology/\n");
  }

  // ===== Deploy VideoRegistry =====
  console.log("━━━ Step 1/3: Deploying VideoRegistry ━━━");
  const VideoRegistry = await hre.ethers.getContractFactory("VideoRegistry");
  const videoRegistry = await VideoRegistry.deploy();
  await videoRegistry.waitForDeployment();
  const videoRegistryAddress = await videoRegistry.getAddress();
  console.log("✅ VideoRegistry deployed to:", videoRegistryAddress);

  // ===== Deploy TrackingLedger =====
  console.log("\n━━━ Step 2/3: Deploying TrackingLedger ━━━");
  const TrackingLedger = await hre.ethers.getContractFactory("TrackingLedger");
  const trackingLedger = await TrackingLedger.deploy();
  await trackingLedger.waitForDeployment();
  const trackingLedgerAddress = await trackingLedger.getAddress();
  console.log("✅ TrackingLedger deployed to:", trackingLedgerAddress);

  // ===== Deploy AlertManager =====
  console.log("\n━━━ Step 3/3: Deploying AlertManager ━━━");
  const AlertManager = await hre.ethers.getContractFactory("AlertManager");
  const alertManager = await AlertManager.deploy();
  await alertManager.waitForDeployment();
  const alertManagerAddress = await alertManager.getAddress();
  console.log("✅ AlertManager deployed to:", alertManagerAddress);

  // ===== Save Deployed Addresses =====
  const deployedAddresses = {
    network: hre.network.name,
    chainId: hre.network.config.chainId || 31337,
    deployer: deployer.address,
    deployedAt: new Date().toISOString(),
    contracts: {
      VideoRegistry: videoRegistryAddress,
      TrackingLedger: trackingLedgerAddress,
      AlertManager: alertManagerAddress,
    },
  };

  const outputPath = path.join(__dirname, "..", "deployed-addresses.json");
  fs.writeFileSync(outputPath, JSON.stringify(deployedAddresses, null, 2));
  console.log("\n📦 Addresses saved to:", outputPath);

  // ===== Post-deploy Summary =====
  console.log("\n╔════════════════════════════════════════════════╗");
  console.log("║          DEPLOYMENT SUMMARY                    ║");
  console.log("╠════════════════════════════════════════════════╣");
  console.log(`║ VideoRegistry:  ${videoRegistryAddress}  ║`);
  console.log(`║ TrackingLedger: ${trackingLedgerAddress}  ║`);
  console.log(`║ AlertManager:   ${alertManagerAddress}  ║`);
  console.log("╚════════════════════════════════════════════════╝");

  // ===== Verify on Testnet/Mainnet =====
  if (
    hre.network.name !== "hardhat" &&
    hre.network.name !== "localhost"
  ) {
    console.log("\n⏳ Waiting for block confirmations before verification...");

    try {
      await videoRegistry.deploymentTransaction().wait(6);
    } catch (e) {
      console.log("   Could not wait for confirmations:", e.message);
    }

    console.log("\n📝 Verifying contracts on PolygonScan...");
    const contracts = [
      { name: "VideoRegistry", address: videoRegistryAddress },
      { name: "TrackingLedger", address: trackingLedgerAddress },
      { name: "AlertManager", address: alertManagerAddress },
    ];

    for (const contract of contracts) {
      try {
        await hre.run("verify:verify", {
          address: contract.address,
          constructorArguments: [],
        });
        console.log(`✅ ${contract.name} verified`);
      } catch (error) {
        if (error.message.includes("Already Verified")) {
          console.log(`✅ ${contract.name} already verified`);
        } else {
          console.log(`⚠️  ${contract.name} verification failed:`, error.message);
        }
      }
    }
  }

  console.log("\n🎉 Deployment complete!\n");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("❌ Deployment failed:", error);
    process.exit(1);
  });
